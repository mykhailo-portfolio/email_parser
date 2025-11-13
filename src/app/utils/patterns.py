# src/app/utils/patterns.py
"""
Canonical phrase pools for classification.

These lists are intentionally curated:
- lowercased and punctuation-normalized (straight ASCII quotes)
- no overly generic single words (e.g., "reject", "declined")
- focused on stable multi-word constructions to reduce false positives

`filters.classify_first_hit` will apply the same normalization to
both phrases and email body (head) before exact substring matching.
"""

from __future__ import annotations

# ---------------------------
# Positive (approve / advance)
# ---------------------------
PHRASES_POS: list[str] = [
    # EN — advance/approve signals
    "we would like to proceed",
    "we'd like to proceed",
    "move forward with your application",
    "we will move forward with your application",
    "move you to the next round",
    "proceed to the interview stage",
    "advance to the next step",
    "advance your application",
    "progress your application",
    "we are pleased to inform you",
    "we're pleased to inform you",
    "successful application",
    "invite you to interview",
    "invite you to the next stage",
    "schedule an interview",
    "we would like to schedule an interview",
    "shortlisted",
    "approve", "approved",
    "we were impressed with your background",
    "we're impressed with your background",

    # RU — позитивные маркеры
    "пригласить на интервью",
    "приглашаем на собеседование",
    "двигаться дальше с вашей заявкой",
    "двигаемся дальше",
    "прошли на следующий этап",
    "успешно прошли отбор",

    # UA — позитивные маркеры
    "запросити на співбесіду",
    "запрошуємо на співбесіду",
    "рухатись далі із заявкою",
    "рухаємось далі",
    "пройшли на наступний етап",
    "успішно пройшли відбір",
]

# ---------------------------
# Negative (decline / stop)
# ---------------------------
PHRASES_NEG: list[str] = [
    # EN — decline/stop signals
    "We decided to move forward with another candidate",
    "we regret to inform you",
    "we are sorry to inform you",
    "we're sorry to inform you",
    "we will not be moving forward",
    "we will not move forward",
    "not moving forward with your application",
    "decided not to proceed",
    "unable to move forward",
    "not to move forward",
    "with other candidate",
    "no longer under consideration",
    "not selected for this position",
    "position has been filled",
    "application was unsuccessful",
    "your application was unsuccessful",
    "will not be proceeding",
    "better fit for other candidates",
    "declined", "decline",

    # Keep a single-word catch only for very strong signals; use carefully.
    # (If it causes noise later, remove.)
    "unfortunately",

    # RU — негативные маркеры
    "к сожалению",
    "вынуждены отказать",
    "вынуждены отказать вам",
    "решили не продолжать",
    "не можем продолжить процесс",
    "не можем продолжить рассмотрение",
    "позиция закрыта",
    "ваша заявка отклонена",
    "заявка была отклонена",
    "не прошли на следующий этап",

    # UA — негативные маркеры
    "на жаль",
    "вимушені відмовити",
    "вирішили не продовжувати",
    "не можемо продовжити процес",
    "позицію закрито",
    "вашу заявку відхилено",
    "заявка була відхилена",
    "не пройшли на наступний етап",
]

SKIP_HINTS: list[str] = [
    # Job aggregators / alerts / newsletters (EN)
    "job alert", "job alerts", "new jobs", "jobs you may be interested in",
    "similar jobs", "recommended jobs", "hottest jobs",
    "linkedin jobs", "indeed jobs", "glassdoor jobs",
    "weekly digest", "daily digest", "job digest", "newsletter", "roundup",
    "career recommendations", "job recommendations", "under review", "If your application",
    "due to high number",

    # Aggregators / brands (keep generic, normalized)
    "linkedin", "indeed", "glassdoor", "ziprecruiter", "workable", "smartrecruiters",

    # OTP / 2FA / verification (EN)
    "otp", "one time password", "one-time password", "verification code",
    "two factor authentication", "2fa", "login code", "security code",
    "use this code", "your code is", "confirm your login", "sign in code",
    "pass code", "code will expire", "confirm your identity",

    # RU / UA — digests / aggregators / newsletters
    "новые вакансии", "подборка вакансий", "рассылка вакансий",
    "підбірка вакансій", "розсилка вакансій",

    # RU / UA — OTP / 2FA
    "одноразовый пароль", "код подтверждения", "код для входа",
    "двухфакторная аутентификация", "2fa", "перевірочний код",
    "код підтвердження", "код входу", "одноразовий пароль",
]

# Explicit export surface
__all__ = ["PHRASES_POS", "PHRASES_NEG", "SKIP_HINTS"]
