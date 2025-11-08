"""
Main service entry point with scheduler and health check support.
"""

from __future__ import annotations
import sys
from pathlib import Path

# ---- ensure src/ is importable when running the file directly
PROJ_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJ_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app.config import _load_env, _init_clients
from app.logging import logger, setup_logging
from app.auth import TokenExpiredError
from app.scheduler import PipelineScheduler
from app.health import HealthCheckServer
# Import pipeline function directly to avoid circular dependencies


def create_pipeline_wrapper(cfg):
    """Create a pipeline function that uses shared clients."""
    # Initialize clients once
    try:
        sheets, gmail, storage = _init_clients(cfg)
    except TokenExpiredError:
        logger.error("Failed to initialize clients - token expired")
        raise
    
    def pipeline_func():
        """Pipeline function that uses pre-initialized clients."""
        from app.config import _load_env
        from app.utils.filters import filter_by_company, classify_latest
        
        # Reload config in case it changed
        current_cfg = _load_env()
        
        try:
            # ---- 1) Companies from Google Sheets
            rows = sheets.fetch_pending_companies(
                spreadsheet_id=current_cfg["SHEET_ID"],
                sheet_name=current_cfg["SHEET_TAB"],
                start_row=current_cfg["START_ROW"],
            )
            companies = [name for _, name in rows]
            
            if not companies:
                return  # No companies - skip logging
            
            # ---- 2) New Gmail message ids since pointer
            ids, head_id, has_more = gmail.collect_new_messages_once(
                storage=storage,
                pointer_key=current_cfg["POINTER_KEY"],
                limit=current_cfg["BATCH_LIMIT"],
                query=current_cfg["GMAIL_QUERY"],
            )
            
            if not ids:
                return  # No new messages - skip logging
            
            # ---- 3) Message briefs
            briefs = gmail.get_message_briefs(ids)
            
            if not briefs:
                gmail.advance_pointer_after_processing(storage, head_id, pointer_key=current_cfg["POINTER_KEY"])
                logger.warning("No briefs retrieved from messages")
                return
            
            # ---- 4) Stage-1: company relevance
            related = filter_by_company(briefs, companies)
            matched_msgs = sum(len(v) for v in related.values())
            
            if not related:
                gmail.advance_pointer_after_processing(storage, head_id, pointer_key=current_cfg["POINTER_KEY"])
                return  # No company matches - skip logging
            
            # ---- 5) Stage-2: classification
            classified = classify_latest(related)
            
            def _count(bucket: str) -> int:
                return sum(len(v) for v in classified.get(bucket, {}).values())
            
            count_approve = _count("approve")
            count_decline = _count("decline")
            count_review = _count("review")
            
            # Only log if there are actual changes
            if not (count_approve or count_decline or count_review):
                gmail.advance_pointer_after_processing(storage, head_id, pointer_key=current_cfg["POINTER_KEY"])
                return  # No changes - skip logging
            
            # Log pipeline execution with changes
            logger.info(f"Processing {matched_msgs} messages for {len(related)} companies")
            logger.info(f"Classification: approve={count_approve}, decline={count_decline}, review={count_review}")
            
            # ---- 6) Update Google Sheets
            if count_approve or count_decline:
                from app.sheets.writer import update_sheet_statuses
                update_sheet_statuses(
                    sheets=sheets,
                    sheet_id=current_cfg["SHEET_ID"],
                    sheet_tab=current_cfg["SHEET_TAB"],
                    results=classified,
                )
                logger.info(f"Updated {count_approve + count_decline} statuses in column C")
            
            if count_review:
                from app.sheets.writer import update_sheet_review
                update_sheet_review(
                    sheets=sheets,
                    sheet_id=current_cfg["SHEET_ID"],
                    sheet_tab=current_cfg["SHEET_TAB"],
                    results=classified,
                )
                logger.info(f"Updated {count_review} review flags in column B")
            
            # Advance pointer after successful processing
            gmail.advance_pointer_after_processing(storage, head_id, pointer_key=current_cfg["POINTER_KEY"])
            
        except Exception as e:
            logger.exception(f"Pipeline execution failed: {e}")
            raise
    
    return pipeline_func


def main() -> None:
    """Main service entry point."""
    health_server = None
    scheduler = None
    try:
        # Setup basic logging first (before loading full config to avoid logs before setup)
        import os
        from dotenv import load_dotenv
        load_dotenv()
        log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()
        log_file = os.getenv("LOG_FILE", "").strip() or None
        
        setup_logging(
            log_level=log_level,
            log_file=log_file,
        )
        
        # Now load full configuration (this may log, but logging is already set up)
        cfg = _load_env()
        
        logger.info("Starting email parser service")
        
        # Initialize scheduler if enabled
        scheduler = None
        if cfg["SCHEDULER_ENABLED"]:
            try:
                pipeline_func = create_pipeline_wrapper(cfg)
                scheduler = PipelineScheduler(
                    pipeline_func=pipeline_func,
                    interval_seconds=cfg["SCHEDULER_INTERVAL"],
                )
                scheduler.start()
                logger.info(f"Scheduler started with interval {cfg['SCHEDULER_INTERVAL']}s")
            except TokenExpiredError:
                logger.error("Cannot start scheduler - token expired")
                raise
        
        # Initialize health check server if enabled
        health_server = None
        if cfg["HEALTH_CHECK_ENABLED"]:
            try:
                def health_func(*args, **kwargs):
                    """Health check function that accepts any arguments for compatibility."""
                    if scheduler:
                        return scheduler.get_health()
                    return {"status": "running", "scheduler": "disabled"}
                
                health_server = HealthCheckServer(
                    port=cfg["HEALTH_CHECK_PORT"],
                    health_func=health_func,
                )
                health_server.start()
                logger.info(f"Health check server started on port {cfg['HEALTH_CHECK_PORT']}")
            except Exception as e:
                logger.warning(f"Failed to start health check server: {e}")
        
        # Wait for scheduler or run once
        if scheduler:
            try:
                scheduler.wait()
            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                scheduler.stop()
        else:
            # Run once if scheduler is disabled
            logger.info("Scheduler disabled, running pipeline once")
            from app.pipeline.run import main as run_pipeline
            run_pipeline()
        
    except KeyboardInterrupt:
        logger.info("Service interrupted by user")
    except Exception as e:
        logger.exception(f"Service failed: {e}")
        raise
    finally:
        if health_server:
            health_server.stop()
        logger.info("Service stopped")


if __name__ == "__main__":
    main()

