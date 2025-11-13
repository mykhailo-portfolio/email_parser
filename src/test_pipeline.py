"""
Тестовый скрипт для запуска пайплайна с детальным логированием.

Запускает полный цикл каждые 5 минут в течение 10 минут (2-3 итерации).
Не записывает данные в таблицу, только выводит детальную информацию о классификации.
"""

from __future__ import annotations
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

# ---- ensure src/ is importable when running the file directly
PROJ_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJ_ROOT
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from app.config import _load_env, _init_clients, Config
from app.logging import logger, setup_logging
from app.utils.filters import filter_by_company, classify_latest
from app.utils.transform import normalize_soft
from app.utils.patterns import PHRASES_POS, PHRASES_NEG
from app.auth import TokenExpiredError


def analyze_classification_triggers(
    email: dict,
    company: str,
    bucket: str
) -> Dict[str, Any]:
    """
    Анализирует, какие фразы триггернули классификацию для письма.

    Args:
        email: Словарь с данными письма
        company: Название компании
        bucket: Категория классификации (approve/decline/review)

    Returns:
        Словарь с детальной информацией о триггерах
    """
    head_norm = normalize_soft(email.get("head", ""))
    subject_norm = normalize_soft(email.get("subject", ""))

    # Нормализуем фразы
    pos_norm = [normalize_soft(p) for p in PHRASES_POS if p]
    neg_norm = [normalize_soft(p) for p in PHRASES_NEG if p]

    # Ищем все совпадения
    found_pos = []
    found_neg = []

    for phrase in pos_norm:
        if phrase and phrase in head_norm:
            # Находим позицию в тексте
            pos = head_norm.find(phrase)
            found_pos.append({
                "phrase": phrase,
                "position": pos,
                "original": next((p for p in PHRASES_POS if normalize_soft(p) == phrase), phrase)
            })

    for phrase in neg_norm:
        if phrase and phrase in head_norm:
            pos = head_norm.find(phrase)
            found_neg.append({
                "phrase": phrase,
                "position": pos,
                "original": next((p for p in PHRASES_NEG if normalize_soft(p) == phrase), phrase)
            })

    # Определяем, какая фраза была первой
    first_pos = min(found_pos, key=lambda x: x["position"]) if found_pos else None
    first_neg = min(found_neg, key=lambda x: x["position"]) if found_neg else None

    trigger_info = {
        "company": company,
        "bucket": bucket,
        "email_id": email.get("id", "unknown"),
        "from": email.get("from", "unknown"),
        "subject": email.get("subject", "unknown"),
        "found_positive": found_pos,
        "found_negative": found_neg,
        "first_positive": first_pos,
        "first_negative": first_neg,
        "decision_reason": "",
    }

    # Определяем причину решения
    if bucket == "approve":
        if first_pos and first_neg:
            if first_pos["position"] < first_neg["position"]:
                trigger_info["decision_reason"] = f"Позитивная фраза '{first_pos['original']}' найдена раньше негативной"
            else:
                trigger_info["decision_reason"] = f"Негативная фраза '{first_neg['original']}' найдена раньше, но классифицировано как approve (ошибка?)"
        elif first_pos:
            trigger_info["decision_reason"] = f"Найдена только позитивная фраза: '{first_pos['original']}'"
        else:
            trigger_info["decision_reason"] = "Классифицировано как approve, но позитивные фразы не найдены (ошибка?)"
    elif bucket == "decline":
        if first_pos and first_neg:
            if first_neg["position"] < first_pos["position"]:
                trigger_info["decision_reason"] = f"Негативная фраза '{first_neg['original']}' найдена раньше позитивной"
            else:
                trigger_info["decision_reason"] = f"Позитивная фраза '{first_pos['original']}' найдена раньше, но классифицировано как decline (ошибка?)"
        elif first_neg:
            trigger_info["decision_reason"] = f"Найдена только негативная фраза: '{first_neg['original']}'"
        else:
            trigger_info["decision_reason"] = "Классифицировано как decline, но негативные фразы не найдены (ошибка?)"
    else:  # review
        if not found_pos and not found_neg:
            trigger_info["decision_reason"] = "Не найдено ни позитивных, ни негативных фраз - требуется ручной просмотр"
        else:
            trigger_info["decision_reason"] = f"Найдены и позитивные ({len(found_pos)}), и негативные ({len(found_neg)}) фразы, но решение неоднозначно"

    return trigger_info


def print_classification_details(classified: Dict[str, Dict[str, List[dict]]]) -> None:
    """
    Выводит детальную информацию о классификации для каждой компании.

    Args:
        classified: Результат classify_latest()
    """
    print("\n" + "=" * 80)
    print("ДЕТАЛЬНАЯ ИНФОРМАЦИЯ О КЛАССИФИКАЦИИ")
    print("=" * 80)

    for bucket in ["approve", "decline", "review"]:
        companies = classified.get(bucket, {})
        if not companies:
            continue

        print(f"\n📋 КАТЕГОРИЯ: {bucket.upper()}")
        print("-" * 80)

        for company, emails in companies.items():
            if not emails:
                continue

            # Берем последнее письмо (самое новое)
            email = emails[0] if emails else None
            if not email:
                continue

            trigger_info = analyze_classification_triggers(email, company, bucket)

            print(f"\n🏢 Компания: {trigger_info['company']}")
            print(f"   От: {trigger_info['from']}")
            print(f"   Тема: {trigger_info['subject']}")
            print(f"   Email ID: {trigger_info['email_id']}")
            print(f"\n   💡 Решение: {trigger_info['decision_reason']}")

            if trigger_info['found_positive']:
                print(f"\n   ✅ Найденные ПОЗИТИВНЫЕ фразы ({len(trigger_info['found_positive'])}):")
                for phrase_info in trigger_info['found_positive']:
                    marker = "👉" if phrase_info == trigger_info['first_positive'] else "  "
                    print(f"      {marker} '{phrase_info['original']}' (позиция: {phrase_info['position']})")

            if trigger_info['found_negative']:
                print(f"\n   ❌ Найденные НЕГАТИВНЫЕ фразы ({len(trigger_info['found_negative'])}):")
                for phrase_info in trigger_info['found_negative']:
                    marker = "👉" if phrase_info == trigger_info['first_negative'] else "  "
                    print(f"      {marker} '{phrase_info['original']}' (позиция: {phrase_info['position']})")

            if not trigger_info['found_positive'] and not trigger_info['found_negative']:
                print(f"\n   ⚠️  Фразы не найдены - требуется ручной просмотр")

            # Показываем первые 500 символов head для контекста
            head = email.get("head", "")
            if head:
                preview = head[:500] + "..." if len(head) > 500 else head
                print(f"\n   📄 Превью письма (первые 500 символов):")
                print(f"      {preview.replace(chr(10), ' ').replace(chr(13), '')}")

            print()

    print("=" * 80 + "\n")


def run_test_iteration(
    iteration: int,
    total_iterations: int,
    cfg: Config,
    sheets,
    gmail,
    storage,
) -> None:
    """
    Запускает одну итерацию тестового пайплайна.

    Args:
        iteration: Номер текущей итерации
        total_iterations: Общее количество итераций
        cfg: Конфигурация (загружена один раз)
        sheets: SheetsClient (создан один раз)
        gmail: GmailClient (создан один раз)
        storage: PointerStorage (создан один раз, сохраняется между итерациями)
    """
    logger.info(f"\n{'='*80}")
    logger.info(f"ТЕСТОВАЯ ИТЕРАЦИЯ {iteration}/{total_iterations}")
    logger.info(f"{'='*80}\n")

    # Показываем текущий указатель для отладки
    current_pointer = storage.get(cfg["POINTER_KEY"])
    if current_pointer:
        logger.info(f"📍 Текущий указатель: {current_pointer[:20]}...")
    else:
        logger.info("📍 Указатель не установлен (первый запуск)")

    try:
        # ---- 1) Companies from Google Sheets
        logger.info("Загрузка компаний из Google Sheets...")
        try:
            rows = sheets.fetch_pending_companies(
                spreadsheet_id=cfg["SHEET_ID"],
                sheet_name=cfg["SHEET_TAB"],
                start_row=cfg["START_ROW"],
            )
            companies = [name for _, name in rows]
            logger.info(f"✅ Загружено {len(companies)} компаний: {', '.join(companies[:5])}{'...' if len(companies) > 5 else ''}")
        except Exception as e:
            logger.error(f"❌ Ошибка при загрузке компаний: {e}")
            return

        if not companies:
            logger.warning("⚠️  Нет компаний для обработки")
            return

        # ---- 2) New Gmail message ids since pointer
        logger.info("Поиск новых писем в Gmail...")
        try:
            ids, head_id, has_more = gmail.collect_new_messages_once(
                storage=storage,
                pointer_key=cfg["POINTER_KEY"],
                limit=cfg["BATCH_LIMIT"],
                query=cfg["GMAIL_QUERY"],
            )
            logger.info(f"✅ Найдено {len(ids)} новых писем (has_more={has_more})")
        except Exception as e:
            logger.error(f"❌ Ошибка при поиске писем: {e}")
            return

        if not ids:
            logger.info("ℹ️  Нет новых писем для обработки")
            return

        # ---- 3) Message briefs
        logger.info("Получение содержимого писем...")
        try:
            briefs = gmail.get_message_briefs(ids)
            logger.info(f"✅ Получено {len(briefs)} писем")
        except Exception as e:
            logger.error(f"❌ Ошибка при получении писем: {e}")
            return

        if not briefs:
            logger.warning("⚠️  Нет писем для обработки")
            return

        # ---- 4) Stage-1: company relevance
        logger.info("Фильтрация писем по компаниям...")
        related = filter_by_company(briefs, companies)
        matched_msgs = sum(len(v) for v in related.values())
        logger.info(f"✅ Найдено совпадений: {len(related)} компаний, {matched_msgs} писем")

        if not related:
            logger.info("ℹ️  Нет писем, связанных с компаниями")
            # Продвигаем указатель даже если нет совпадений
            gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])
            return

        # ---- 5) Stage-2: classification
        logger.info("Классификация писем...")
        classified = classify_latest(related)

        def _count(bucket: str) -> int:
            return sum(len(v) for v in classified.get(bucket, {}).values())

        count_approve = _count("approve")
        count_decline = _count("decline")
        count_review = _count("review")

        logger.info(f"✅ Результаты классификации:")
        logger.info(f"   ✅ Approve: {count_approve}")
        logger.info(f"   ❌ Decline: {count_decline}")
        logger.info(f"   ⚠️  Review: {count_review}")

        # ---- 6) Детальный вывод (БЕЗ записи в таблицу)
        print_classification_details(classified)

        # Продвигаем указатель
        gmail.advance_pointer_after_processing(storage, head_id, pointer_key=cfg["POINTER_KEY"])
        new_pointer = storage.get(cfg["POINTER_KEY"])
        logger.info(f"✅ Указатель продвинут: {new_pointer[:20] if new_pointer else 'N/A'}...")
        logger.info("✅ Готово к следующей итерации")

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка в итерации {iteration}: {e}")


def main() -> None:
    """Главная функция тестового скрипта."""
    print("\n" + "="*80)
    print("ТЕСТОВЫЙ ЗАПУСК ПАЙПЛАЙНА")
    print("="*80)
    print("Режим: ТОЛЬКО ЧТЕНИЕ (без записи в таблицу)")
    print("Длительность: 10 минут")
    print("Интервал: каждые 5 минут")
    print("Ожидаемое количество итераций: 2-3")
    print("="*80 + "\n")

    # Инициализация (один раз для всех итераций)
    try:
        cfg = _load_env()
        setup_logging(
            log_level=cfg["LOG_LEVEL"],
            log_file=cfg["LOG_FILE"],
        )

        logger.info("Инициализация клиентов (один раз для всех итераций)...")
        try:
            sheets, gmail, storage = _init_clients(cfg)
            logger.info("✅ Клиенты инициализированы")
        except TokenExpiredError as e:
            logger.error(
                f"\n{'='*80}\n"
                f"❌ ТОКЕН ИСТЕК - ТРЕБУЕТСЯ ПЕРЕАВТОРИЗАЦИЯ\n"
                f"{'='*80}\n"
                f"Для продолжения работы выполните:\n"
                f"  python scripts/bootstrap_oauth.py\n\n"
                f"Или установите AUTO_REAUTHORIZE=true в .env для автоматической переавторизации.\n"
                f"{'='*80}\n"
            )
            return

        # Показываем информацию о storage
        storage_type = type(storage).__name__
        logger.info(f"📦 Используется storage: {storage_type}")
        if storage_type == "InMemoryEmailStorage":
            logger.warning(
                "⚠️  ВНИМАНИЕ: Используется InMemory storage. "
                "Указатель будет сохраняться только между итерациями в рамках одного запуска. "
                "Для персистентного хранения используйте Redis (USE_REDIS=true)."
            )

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка при инициализации: {e}")
        return

    # Настройка таймингов
    duration_minutes = 10
    interval_minutes = 2
    interval_seconds = interval_minutes * 60
    start_time = time.time()
    end_time = start_time + (duration_minutes * 60)
    iteration = 0

    # Первая итерация сразу
    iteration += 1
    run_test_iteration(iteration, 3, cfg, sheets, gmail, storage)

    # Последующие итерации с интервалом
    while time.time() < end_time:
        remaining_time = end_time - time.time()
        if remaining_time < interval_seconds:
            logger.info(f"⏱️  Осталось {remaining_time/60:.1f} минут - недостаточно для следующей итерации")
            break

        logger.info(f"⏳ Ожидание {interval_minutes} минут до следующей итерации...")
        time.sleep(interval_seconds)

        if time.time() < end_time:
            iteration += 1
            run_test_iteration(iteration, 3, cfg, sheets, gmail, storage)

    total_time = (time.time() - start_time) / 60
    print("\n" + "="*80)
    print(f"ТЕСТОВЫЙ ЗАПУСК ЗАВЕРШЕН")
    print(f"Всего итераций: {iteration}")
    print(f"Общее время: {total_time:.1f} минут")
    
    # Показываем финальный указатель
    final_pointer = storage.get(cfg["POINTER_KEY"])
    if final_pointer:
        print(f"Финальный указатель: {final_pointer[:30]}...")
    print("="*80 + "\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Прервано пользователем")
        sys.exit(0)
    except Exception as e:
        logger.exception(f"Критическая ошибка: {e}")
        sys.exit(1)

