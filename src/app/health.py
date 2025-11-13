"""
Health check endpoint for monitoring pipeline status.
"""

from __future__ import annotations
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Optional, Callable
from threading import Thread
from app.logging import logger


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoint."""
    
    health_func: Optional[Callable[[], dict]] = None
    
    def do_GET(self) -> None:
        """Handle GET requests."""
        if self.path == "/health" or self.path == "/health/":
            self._handle_health()
        elif self.path == "/" or self.path == "/status":
            self._handle_status()
        else:
            self._send_response(404, {"error": "Not found"})
    
    def _handle_health(self) -> None:
        """Handle /health endpoint."""
        if self.health_func:
            try:
                health_data = self.health_func()
                status_code = 200 if health_data.get("status") == "healthy" else 503
                self._send_response(status_code, health_data)
            except BrokenPipeError:
                # Client closed connection before response was sent - this is normal
                pass
            except Exception as e:
                logger.error(f"Health check failed: {e}")
                try:
                    self._send_response(500, {"status": "error", "error": str(e)})
                except BrokenPipeError:
                    # Client closed connection - ignore
                    pass
        else:
            try:
                self._send_response(503, {"status": "unavailable", "message": "Health check not configured"})
            except BrokenPipeError:
                pass
    
    def _handle_status(self) -> None:
        """Handle /status endpoint."""
        try:
            self._send_response(200, {"service": "email-parser", "status": "running"})
        except BrokenPipeError:
            pass
    
    def _send_response(self, status_code: int, data: dict) -> None:
        """Send JSON response."""
        try:
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
        except BrokenPipeError:
            # Client closed connection before response was sent - this is normal
            pass
    
    def log_message(self, format: str, *args) -> None:
        """Override to use our logger instead of default."""
        logger.debug(f"HTTP {format % args}")


class HealthCheckServer:
    """
    Simple HTTP server for health checks.
    
    Provides endpoints:
    - GET /health - Detailed health check
    - GET /status - Simple status check
    """
    
    def __init__(
        self,
        port: int = 8080,
        health_func: Optional[Callable[[], dict]] = None,
    ) -> None:
        """
        Initialize health check server.
        
        Args:
            port: Port to listen on
            health_func: Function that returns health status dict
        """
        self.port = port
        self.server: Optional[HTTPServer] = None
        self.thread: Optional[Thread] = None
        HealthCheckHandler.health_func = health_func
    
    def start(self) -> None:
        """Start health check server in background thread."""
        if self.server:
            logger.warning("Health check server is already running")
            return
        
        try:
            self.server = HTTPServer(("0.0.0.0", self.port), HealthCheckHandler)
            self.thread = Thread(target=self._run_server, daemon=True)
            self.thread.start()
            logger.info(f"Health check server started on port {self.port}")
        except Exception as e:
            logger.error(f"Failed to start health check server: {e}")
            raise
    
    def _run_server(self) -> None:
        """Run HTTP server."""
        if self.server:
            try:
                self.server.serve_forever()
            except Exception as e:
                logger.error(f"Health check server error: {e}")
    
    def stop(self) -> None:
        """Stop health check server."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            logger.info("Health check server stopped")

