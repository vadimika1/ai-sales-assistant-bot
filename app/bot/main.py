from __future__ import annotations

import asyncio
from contextlib import suppress
import logging
from functools import lru_cache
from typing import cast
from urllib.parse import urlsplit

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramUnauthorizedError
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from app.bot.client import AssistantApiClient, AssistantApiClientError
from app.bot.pending_edits import PendingEditsStore
from app.bot.user_locales import (
    DEFAULT_BOT_LOCALE,
    BotLocale,
    SUPPORTED_BOT_LOCALES,
    UserLocalesStore,
)
from app.config import Settings, get_settings
from app.logging_config import configure_logging
from app.preflight import validate_runtime_settings

router = Router()
logger = logging.getLogger(__name__)

INTENT_LABELS = {
    "price": "Цена",
    "timeline": "Сроки",
    "objection": "Возражение",
    "qualification": "Квалификация",
    "general": "Общий запрос",
}

LEAD_STAGE_LABELS = {
    "new": "Новый",
    "qualified": "Квалифицирован",
    "proposal": "Подготовка КП",
    "negotiation": "Переговоры",
    "won": "Сделка выиграна",
    "lost": "Сделка проиграна",
}

NEXT_ACTION_LABELS = {
    "ask_clarifying_question": "Задать уточняющий вопрос",
    "schedule_call": "Назначить звонок",
    "prepare_proposal": "Подготовить предложение",
    "send_follow_up": "Отправить повторное сообщение",
    "handoff_to_manager": "Передать менеджеру",
}


INTENT_LABELS_EN = {
    "price": "Price",
    "timeline": "Timeline",
    "objection": "Objection",
    "qualification": "Qualification",
    "general": "General request",
}

LEAD_STAGE_LABELS_EN = {
    "new": "New",
    "qualified": "Qualified",
    "proposal": "Proposal",
    "negotiation": "Negotiation",
    "won": "Won",
    "lost": "Lost",
}

NEXT_ACTION_LABELS_EN = {
    "ask_clarifying_question": "Ask clarifying question",
    "schedule_call": "Schedule a call",
    "prepare_proposal": "Prepare proposal",
    "send_follow_up": "Send follow-up",
    "handoff_to_manager": "Handoff to manager",
}

TRANSLATIONS: dict[BotLocale, dict[str, str]] = {
    "ru": {
        "start_text": (
            "Привет! Я AI-ассистент для менеджера продаж.\n\n"
            "Команда: <code>/ai ваш текст</code>\n"
            "Я верну вариант ответа, интент и следующий шаг."
        ),
        "choose_language": "Выберите язык интерфейса / Choose interface language:",
        "language_saved": "Язык сохранен: русский.",
        "language_help": "Язык можно изменить в любой момент командой /language.",
        "usage_ai": "Использование: /ai <текст сообщения клиента или ваш черновик>",
        "preparing_suggestion": "Готовлю подсказку...",
        "ai_error_prefix": "Ошибка AI",
        "ai_error_internal": "Ошибка AI: внутренняя ошибка. Попробуйте позже.",
        "reply_header": "Вариант ответа",
        "intent_label": "Интент",
        "lead_stage_label": "Этап лида",
        "next_action_label": "Следующий шаг",
        "confidence_label": "Уверенность",
        "model_label": "Модель",
        "tokens_label": "Токены",
        "invalid_suggestion_data": "Некорректные данные подсказки",
        "generic_error_prefix": "Ошибка",
        "generic_internal_error": "Ошибка: внутренняя ошибка",
        "accepted_short": "Подсказка принята",
        "accepted_full": "✅ Зафиксировано: подсказка принята",
        "rejected_short": "Подсказка отклонена",
        "rejected_full": "❌ Зафиксировано: подсказка отклонена",
        "ok_short": "Ок",
        "edit_request": (
            "✏️ Отправьте следующим сообщением исправленный вариант ответа. "
            "Я сохраню его как отредактированный."
        ),
        "edited_text_required": "Нужен текст исправленного ответа.",
        "feedback_save_error_prefix": "Ошибка сохранения feedback",
        "feedback_save_internal": "Ошибка сохранения feedback: внутренняя ошибка.",
        "edited_saved": "✅ Зафиксировано: ответ отредактирован",
        "language_required_callback": "Сначала выберите язык.",
        "language_command_hint": "Выберите язык интерфейса:",
        "button_accept": "✅ Принять",
        "button_edit": "✏️ Изменить",
        "button_reject": "❌ Отклонить",
    },
    "en": {
        "start_text": (
            "Hi! I'm an AI assistant for sales managers.\n\n"
            "Command: <code>/ai your text</code>\n"
            "I'll return a reply draft, intent, and next action."
        ),
        "choose_language": "Choose interface language / Выберите язык интерфейса:",
        "language_saved": "Language saved: English.",
        "language_help": "You can change language any time with /language.",
        "usage_ai": "Usage: /ai <client message text or your draft>",
        "preparing_suggestion": "Preparing suggestion...",
        "ai_error_prefix": "AI error",
        "ai_error_internal": "AI error: internal error. Try again later.",
        "reply_header": "Reply Draft",
        "intent_label": "Intent",
        "lead_stage_label": "Lead Stage",
        "next_action_label": "Next Action",
        "confidence_label": "Confidence",
        "model_label": "Model",
        "tokens_label": "Tokens",
        "invalid_suggestion_data": "Invalid suggestion payload",
        "generic_error_prefix": "Error",
        "generic_internal_error": "Error: internal error",
        "accepted_short": "Suggestion accepted",
        "accepted_full": "✅ Saved: suggestion accepted",
        "rejected_short": "Suggestion rejected",
        "rejected_full": "❌ Saved: suggestion rejected",
        "ok_short": "OK",
        "edit_request": (
            "✏️ Send your corrected reply in the next message. "
            "I'll save it as an edited version."
        ),
        "edited_text_required": "Please send the corrected reply text.",
        "feedback_save_error_prefix": "Failed to save feedback",
        "feedback_save_internal": "Failed to save feedback: internal error.",
        "edited_saved": "✅ Saved: reply edited",
        "language_required_callback": "Choose language first.",
        "language_command_hint": "Choose interface language:",
        "button_accept": "✅ Accept",
        "button_edit": "✏️ Edit",
        "button_reject": "❌ Reject",
    },
}


def get_text(locale: BotLocale, key: str) -> str:
    catalog = TRANSLATIONS.get(locale, TRANSLATIONS[DEFAULT_BOT_LOCALE])
    return catalog.get(key, key)


def parse_locale_callback_data(callback_data: str | None) -> BotLocale | None:
    if not callback_data or not callback_data.startswith("lang:"):
        return None

    raw_locale = callback_data.split(":", maxsplit=1)[1].strip().lower()
    if raw_locale not in SUPPORTED_BOT_LOCALES:
        return None
    return cast(BotLocale, raw_locale)


def resolve_locale_labels(locale: BotLocale, ru_labels: dict[str, str], en_labels: dict[str, str]) -> dict[str, str]:
    if locale == "en":
        return en_labels
    return ru_labels


def build_actions_keyboard(suggestion_id: int, locale: BotLocale) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=get_text(locale, "button_accept"),
                    callback_data=f"ai_accept:{suggestion_id}",
                ),
                InlineKeyboardButton(
                    text=get_text(locale, "button_edit"),
                    callback_data=f"ai_edit:{suggestion_id}",
                ),
                InlineKeyboardButton(
                    text=get_text(locale, "button_reject"),
                    callback_data=f"ai_reject:{suggestion_id}",
                ),
            ]
        ]
    )


def build_language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Русский", callback_data="lang:ru"),
                InlineKeyboardButton(text="English", callback_data="lang:en"),
            ]
        ]
    )


def get_api_client() -> AssistantApiClient:
    settings = get_settings()
    return AssistantApiClient(
        base_url=settings.api_base_url,
        timeout_seconds=settings.openai_timeout_seconds,
        service_token=settings.api_service_token,
        max_retries=settings.bot_api_max_retries,
        retry_base_ms=settings.bot_api_retry_base_ms,
    )


@lru_cache
def get_pending_edits_store() -> PendingEditsStore:
    settings = get_settings()
    return PendingEditsStore(settings.database_url_resolved)


@lru_cache
def get_user_locales_store() -> UserLocalesStore:
    settings = get_settings()
    return UserLocalesStore(settings.database_url_resolved)


def extract_suggestion_id(callback_data: str | None, prefix: str) -> int | None:
    if not callback_data or not callback_data.startswith(prefix):
        return None

    try:
        return int(callback_data.split(":", maxsplit=1)[1])
    except (IndexError, ValueError):
        return None


def localize_value(value: str, labels: dict[str, str]) -> str:
    return labels.get(value, value)


async def ensure_locale_for_message(message: Message) -> BotLocale | None:
    if not message.from_user:
        return None

    locale_store = get_user_locales_store()
    locale = locale_store.get_locale(message.from_user.id)
    if locale:
        return locale

    await message.answer(get_text(DEFAULT_BOT_LOCALE, "choose_language"), reply_markup=build_language_keyboard())
    return None


async def ensure_locale_for_callback(callback: CallbackQuery) -> BotLocale | None:
    locale_store = get_user_locales_store()
    locale = locale_store.get_locale(callback.from_user.id)
    if locale:
        return locale

    await callback.answer(get_text(DEFAULT_BOT_LOCALE, "language_required_callback"), show_alert=True)
    if callback.message:
        await callback.message.reply(
            get_text(DEFAULT_BOT_LOCALE, "choose_language"),
            reply_markup=build_language_keyboard(),
        )
    return None


def normalize_webhook_path(path: str) -> str:
    cleaned = (path or "").strip()
    if not cleaned:
        return "/telegram/webhook"
    if not cleaned.startswith("/"):
        cleaned = f"/{cleaned}"
    if cleaned == "/":
        return cleaned
    return "/" + cleaned.strip("/")


def build_public_webhook_url(raw_url: str, webhook_path: str) -> str:
    base_url = (raw_url or "").strip().rstrip("/")
    if not base_url:
        raise RuntimeError("BOT_WEBHOOK_URL не задан для webhook режима")

    parsed = urlsplit(base_url)
    if not parsed.scheme or not parsed.netloc:
        raise RuntimeError("BOT_WEBHOOK_URL должен быть полным URL, например https://example.com/hook")

    if parsed.path and parsed.path not in ("", "/"):
        return base_url
    return f"{base_url}{webhook_path}"


@router.message(CommandStart())
async def on_start(message: Message) -> None:
    if not message.from_user:
        return

    locale = get_user_locales_store().get_locale(message.from_user.id)
    if locale is None:
        await message.answer(
            get_text(DEFAULT_BOT_LOCALE, "choose_language"),
            reply_markup=build_language_keyboard(),
        )
        return

    await message.answer(f"{get_text(locale, 'start_text')}\n\n{get_text(locale, 'language_help')}")


@router.message(Command("language"))
async def on_language(message: Message) -> None:
    locale = DEFAULT_BOT_LOCALE
    if message.from_user:
        locale = get_user_locales_store().get_locale(message.from_user.id) or DEFAULT_BOT_LOCALE

    await message.answer(get_text(locale, "language_command_hint"), reply_markup=build_language_keyboard())


@router.callback_query(lambda callback: callback.data and callback.data.startswith("lang:"))
async def on_language_selected(callback: CallbackQuery) -> None:
    locale = parse_locale_callback_data(callback.data)
    if locale is None:
        await callback.answer(get_text(DEFAULT_BOT_LOCALE, "invalid_suggestion_data"), show_alert=True)
        return

    get_user_locales_store().set_locale(callback.from_user.id, locale)
    await callback.answer(get_text(locale, "language_saved"))
    if callback.message:
        with suppress(Exception):
            await callback.message.edit_reply_markup(reply_markup=None)
        await callback.message.reply(f"{get_text(locale, 'start_text')}\n\n{get_text(locale, 'language_help')}")


@router.message(Command("ai"))
async def on_ai(message: Message) -> None:
    locale = await ensure_locale_for_message(message)
    if locale is None:
        return

    command_text = message.text or ""
    parts = command_text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer(get_text(locale, "usage_ai"))
        return

    pending = await message.answer(get_text(locale, "preparing_suggestion"))
    api_client = get_api_client()

    try:
        request_user_id = message.from_user.id if message.from_user else None
        result = await api_client.suggest(parts[1].strip(), user_id=request_user_id)
    except AssistantApiClientError as error:
        logger.warning("Failed to generate suggestion: %s", error)
        await pending.edit_text(f"{get_text(locale, 'ai_error_prefix')}: {error}")
        return
    except Exception:
        logger.exception("Unexpected error while generating suggestion")
        await pending.edit_text(get_text(locale, "ai_error_internal"))
        return

    suggestion = result.data
    suggestion_id = result.meta.suggestion_id
    intent_labels = resolve_locale_labels(locale, INTENT_LABELS, INTENT_LABELS_EN)
    lead_stage_labels = resolve_locale_labels(locale, LEAD_STAGE_LABELS, LEAD_STAGE_LABELS_EN)
    next_action_labels = resolve_locale_labels(locale, NEXT_ACTION_LABELS, NEXT_ACTION_LABELS_EN)
    response_text = (
        f"<b>{get_text(locale, 'reply_header')}</b>\n{suggestion.suggested_reply}\n\n"
        f"<b>{get_text(locale, 'intent_label')}:</b> {localize_value(suggestion.intent, intent_labels)}\n"
        f"<b>{get_text(locale, 'lead_stage_label')}:</b> "
        f"{localize_value(suggestion.lead_stage, lead_stage_labels)}\n"
        f"<b>{get_text(locale, 'next_action_label')}:</b> "
        f"{localize_value(suggestion.next_action, next_action_labels)}\n"
        f"<b>{get_text(locale, 'confidence_label')}:</b> {suggestion.confidence:.2f}\n"
        f"<b>{get_text(locale, 'model_label')}:</b> {result.meta.model}\n"
        f"<b>{get_text(locale, 'tokens_label')}:</b> {result.meta.prompt_tokens}/{result.meta.completion_tokens}/"
        f"{result.meta.total_tokens}"
    )

    if suggestion_id:
        await pending.edit_text(response_text, reply_markup=build_actions_keyboard(suggestion_id, locale))
    else:
        await pending.edit_text(response_text)


@router.callback_query(lambda callback: callback.data and callback.data.startswith("ai_accept:"))
async def on_accept(callback: CallbackQuery) -> None:
    locale = await ensure_locale_for_callback(callback)
    if locale is None:
        return

    suggestion_id = extract_suggestion_id(callback.data, "ai_accept:")
    if not suggestion_id:
        await callback.answer(get_text(locale, "invalid_suggestion_data"), show_alert=True)
        return

    api_client = get_api_client()

    try:
        await api_client.feedback(suggestion_id=suggestion_id, manager_action="accepted")
    except AssistantApiClientError as error:
        logger.warning("Failed to save accepted feedback: %s", error)
        await callback.answer(f"{get_text(locale, 'generic_error_prefix')}: {error}", show_alert=True)
        return
    except Exception:
        logger.exception("Unexpected error while saving accepted feedback")
        await callback.answer(get_text(locale, "generic_internal_error"), show_alert=True)
        return

    await callback.answer(get_text(locale, "accepted_short"))
    if callback.message:
        await callback.message.reply(get_text(locale, "accepted_full"))


@router.callback_query(lambda callback: callback.data and callback.data.startswith("ai_reject:"))
async def on_reject(callback: CallbackQuery) -> None:
    locale = await ensure_locale_for_callback(callback)
    if locale is None:
        return

    suggestion_id = extract_suggestion_id(callback.data, "ai_reject:")
    if not suggestion_id:
        await callback.answer(get_text(locale, "invalid_suggestion_data"), show_alert=True)
        return

    api_client = get_api_client()

    try:
        await api_client.feedback(suggestion_id=suggestion_id, manager_action="rejected")
    except AssistantApiClientError as error:
        logger.warning("Failed to save rejected feedback: %s", error)
        await callback.answer(f"{get_text(locale, 'generic_error_prefix')}: {error}", show_alert=True)
        return
    except Exception:
        logger.exception("Unexpected error while saving rejected feedback")
        await callback.answer(get_text(locale, "generic_internal_error"), show_alert=True)
        return

    await callback.answer(get_text(locale, "rejected_short"))
    if callback.message:
        await callback.message.reply(get_text(locale, "rejected_full"))


@router.callback_query(lambda callback: callback.data and callback.data.startswith("ai_edit:"))
async def on_edit(callback: CallbackQuery) -> None:
    locale = await ensure_locale_for_callback(callback)
    if locale is None:
        return

    suggestion_id = extract_suggestion_id(callback.data, "ai_edit:")
    if not suggestion_id:
        await callback.answer(get_text(locale, "invalid_suggestion_data"), show_alert=True)
        return

    user_id = callback.from_user.id
    pending_store = get_pending_edits_store()
    pending_store.set_pending(user_id=user_id, suggestion_id=suggestion_id)

    await callback.answer(get_text(locale, "ok_short"))
    if callback.message:
        await callback.message.reply(get_text(locale, "edit_request"))


@router.message()
async def on_edited_reply(message: Message) -> None:
    if not message.from_user:
        return

    user_id = message.from_user.id
    pending_store = get_pending_edits_store()
    suggestion_id = pending_store.get_pending(user_id)
    if not suggestion_id:
        return

    locale = await ensure_locale_for_message(message)
    if locale is None:
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer(get_text(locale, "edited_text_required"))
        return

    if text.startswith("/"):
        return

    api_client = get_api_client()
    try:
        await api_client.feedback(
            suggestion_id=suggestion_id,
            manager_action="edited",
            edited_reply=text,
        )
    except AssistantApiClientError as error:
        logger.warning("Failed to save edited feedback: %s", error)
        await message.answer(f"{get_text(locale, 'feedback_save_error_prefix')}: {error}")
        return
    except Exception:
        logger.exception("Unexpected error while saving edited feedback")
        await message.answer(get_text(locale, "feedback_save_internal"))
        return

    pending_store.clear_pending(user_id)
    await message.answer(get_text(locale, "edited_saved"))


async def _run_bot() -> None:
    settings = get_settings()
    validate_runtime_settings(settings, target="bot")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        me = await bot.get_me()
    except TelegramUnauthorizedError as error:
        raise RuntimeError(
            "Неверный TELEGRAM_BOT_TOKEN. Сгенерируйте новый токен в BotFather и обновите .env."
        ) from error

    logger.info("Bot authorization successful for @%s", me.username)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    if settings.bot_run_mode == "polling":
        await _run_polling(bot=bot, dispatcher=dispatcher, settings=settings)
        return

    await _run_webhook(bot=bot, dispatcher=dispatcher, settings=settings)


async def _run_polling(bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    await bot.delete_webhook(drop_pending_updates=settings.bot_drop_pending_updates)
    logger.info("Bot running in polling mode")
    await dispatcher.start_polling(
        bot,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )


async def _run_webhook(bot: Bot, dispatcher: Dispatcher, settings: Settings) -> None:
    webhook_path = normalize_webhook_path(settings.bot_webhook_path)
    webhook_url = build_public_webhook_url(settings.bot_webhook_url, webhook_path)
    webhook_secret = settings.bot_webhook_secret.strip() or None

    await bot.set_webhook(
        url=webhook_url,
        secret_token=webhook_secret,
        drop_pending_updates=settings.bot_drop_pending_updates,
        allowed_updates=dispatcher.resolve_used_update_types(),
    )

    app = web.Application()
    request_handler = SimpleRequestHandler(
        dispatcher=dispatcher,
        bot=bot,
        secret_token=webhook_secret,
    )
    request_handler.register(app, path=webhook_path)
    setup_application(app, dispatcher, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=settings.bot_webhook_host, port=settings.bot_webhook_port)
    await site.start()

    logger.info(
        "Bot running in webhook mode",
        extra={
            "webhook_url": webhook_url,
            "webhook_host": settings.bot_webhook_host,
            "webhook_port": settings.bot_webhook_port,
            "webhook_path": webhook_path,
        },
    )

    try:
        await asyncio.Event().wait()
    finally:
        with suppress(Exception):
            await bot.delete_webhook(drop_pending_updates=False)
        with suppress(Exception):
            await runner.cleanup()


def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info("Starting Telegram bot process")
    asyncio.run(_run_bot())


if __name__ == "__main__":
    run()
