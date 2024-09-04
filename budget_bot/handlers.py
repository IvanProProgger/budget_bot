import re
import textwrap
from datetime import datetime

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import CallbackContext, ContextTypes

from config.config import Config
from config.logging_config import logger
from db import db
from budget_bot.sheets import GoogleSheetsManager


async def chat_ids_department(department) -> list[str]:
    """Возвращяет chat_id для подгрупп"""

    chat_ids = {
        "head": Config.department_head_chat_id,
        "finance": Config.finance_chat_ids,
        "payers": Config.payers_chat_ids,
        "all": Config.department_head_chat_id
               + Config.finance_chat_ids
               + Config.payers_chat_ids,
    }
    return chat_ids[department]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /start."""

    await update.message.reply_text(
        f"<b>Бот по автоматизации заполнения бюджета</b>\n"
        "<i>Отправьте команду /enter_record и укажите:</i>\n"
        "<i>1)Сумма счёта</i>\n"
        "<i>2)Статья расхода</i>\n"
        "<i>3)Группа расхода</i>\n"
        "<i>4)Партнёр</i>\n"
        "<i>5)Дата оплаты и дата начисления платежа через пробел</i>\n"
        "<i>6)Форма оплаты</i>\n"
        "<i>7)Комментарий к платежу</i>\n"
        "<i>Каждый пункт необходимо указывать строго через запятую.</i>\n\n"
        "<i>Вы можете просмотреть необработанные заявки командой /show_not_processed</i>\n\n"
        "<i>Одобрить заявку можно командой /approve_record указав id заявки</i>\n\n"
        "<i>Отклонить заявку можно командой /reject_record указав id заявки</i>\n\n"
        f"<i>Ваш chat_id - {update.message.chat_id}</i>",
        parse_mode="HTML",
    )


async def submit_record_command(
        update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Обработчик введённого пользователем платежа в соответствии с паттерном:
    1)Сумма счёта: положительное число (возможно с плавающей точкой)
    2)Статья расхода: любая строка из букв и цифр
    3)Группа расхода: любая строка из букв и цифр
    4)Партнёр: любая строка из букв и цифр
    5)Дата: как минимум 2 даты; дата оплаты и дата(ы) начисления платежа
    6)Форма оплаты: любая строка из букв и цифр
    7)Комментарий к платежу: любая строка из букв и цифр
    Добавление платежа в базу данных 'approvals';
    Отправление данных о платеже для одобрения главой отдела.
    """

    initiator_chat_id = update.effective_chat.id
    if not context.args:
        await context.bot.send_message(
            chat_id=initiator_chat_id, text="Необходимо указать данные для платежа."
        )
        raise ValueError(f"Необходимо ввести данные о платеже.")

    pattern = (
        r"((?:0|[1-9]\d*)(?:\.\d+)?)\s*;\s*([^;]+)\s*;\s*([^;]+)\s*;\s*([^;]+)\s*;\s*([^;]+)\s*;"
        r"\s*((?:\d{2}\.\d{2}\s*){1,})\s*;\s*([^;]+)$"
    )
    message = " ".join(context.args)
    match = re.match(pattern, message)
    if not match:
        await context.bot.send_message(
            chat_id=initiator_chat_id,
            text="Неверный формат аргументов. Пожалуйста, следуйте указанному формату.\n"
                 "1)Сумма счёта: положительное число (возможно с плавающей точкой)\n"
                 "2)Статья расхода: любая строка из букв и цифр\n"
                 "3)Группа расхода: любая строка из букв и цифр\n"
                 "4)Партнёр: любая строка из букв и цифр\n"
                 "5)Дата: как минимум 2 даты; дата оплаты и дата(ы) начисления платежа\n"
                 "6)Форма оплаты: любая строка из букв и цифр\n"
                 "7)Комментарий к платежу: любая строка из букв и цифр\n"
        )

    try:
        period_dates = match.group(6).split()
        _ = [
            datetime.strptime(date, "%m.%y").strftime("%m.%Y") for date in period_dates
        ]

    except Exception as e:
        await context.bot.send_message(
            chat_id=initiator_chat_id,
            text=f'Ошибка {e}. Введены неверные даты. Даты вводятся в формате mm.yy. '
                 f'строго через пробел(например: "08.22 10.22"). Пожалуйста, следуйте указанному формату.'
        )
        return

    record_dict = {
        "amount": match.group(1),
        "expense_item": match.group(2),
        "expense_group": match.group(3),
        "partner": match.group(4),
        "comment": match.group(5),
        "period": match.group(6),
        "payment_method": match.group(7),
        "approvals_needed": 1 if float(match.group(1)) < 50000 else 2,
        "approvals_received": 0,
        "status": "Not processed",
        "approved_by": None,
    }

    try:
        async with db:
            approval_id = await db.insert_record(record_dict)
    except Exception as e:
        raise RuntimeError(f"Произошла ошибка при добавлении счёта в базу данных. {e}")

    await create_and_send_approval_message(
        approval_id, initiator_chat_id, record_dict, "head", context=context
    )


async def reject_record_command(
        update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Меняет в базе данных статус платежа на отклонён('Rejected'),
    и отправляет сообщение об отмене ранее одобренного платежа.
    """

    row_id = context.args

    if not row_id:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Пожалуйста, укажите id заявки!")
        return

    if len(row_id) > 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Можно указать только 1 заявку!")
        return

    row_id = row_id[0]

    async with db:
        result = await db.get_row_by_id(row_id)

        if not result:
            raise RuntimeError(f"Запись с id: {row_id} не найдена.")

        await db.update_row_by_id(row_id, {"status": "Rejected"})

    await update.message.reply_text(f"Заявка {row_id} отклонена.")


async def create_and_send_approval_message(
        approval_id,
        initiator_chat_id,
        record,
        department,
        context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Создание кнопок "Одобрить" и "Отклонить", создание и отправка сообщения для одобрения заявки."""

    keyboard = [
        [
            InlineKeyboardButton(
                "Одобрить",
                callback_data=f"approval_"
                              f"{department}_approve_{approval_id}_{initiator_chat_id}",
            )
        ],
        [
            InlineKeyboardButton(
                "Отклонить",
                callback_data=f"approval_"
                              f"{department}_reject_{approval_id}_{initiator_chat_id}",
            )
        ],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = (
        f"Пожалуйста, одобрите запрос на платеж {approval_id}. \nДанные платежа:\n"
        f'сумма: {record["amount"]}\nстатья: {record["expense_item"]}\n'
        f'группа: {record["expense_group"]}\nпартнер: {record["partner"]}\n'
        f'период начисления: {record["period"]}\nформа оплаты: {record["payment_method"]}\n'
        f'комментарий: {record["comment"]}'
    )

    chat_ids = await chat_ids_department(department)
    await send_message_to_chats(chat_ids, message_text, context, reply_markup)


async def create_and_send_payment_message(
        approval_id, approved_users, record, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Создание кнопок "Оплачено",
    создание и отправка сообщения для одобрения заявки.
    """

    keyboard = [[InlineKeyboardButton("Оплачено", callback_data=f"pay_{approval_id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = (
        f"Запрос на платёж заявки {approval_id} одобрен {approved_users} "
        f'{record["approvals_needed"]}/{record["approvals_received"]} раз. Пожалуйста, оплатите заявку. '
        f'Cумма: {record["amount"]}, статья: {record["expense_item"]}, группа: {record["expense_group"]}, '
        f'партнер: {record["partner"]}, период начисления: {record["period"]}, форма оплаты: '
        f'{record["payment_method"]}, комментарий: {record["comment"]}'
    )
    chat_ids = await chat_ids_department("payers")
    await send_message_to_chats(chat_ids, message_text, context, reply_markup)


async def send_message_to_chats(chat_ids, text, context, reply_markup=None):
    """Отправка сообщения в выбранные телеграм-чаты."""

    for chat_id in chat_ids:
        await context.bot.send_message(
            chat_id=chat_id, text=text, reply_markup=reply_markup
        )


async def add_record_to_google_sheet(record) -> None:
    """Функция для добавления строки в таблицу Google Sheet."""

    manager = GoogleSheetsManager()
    await manager.initialize_google_sheets()
    await manager.add_payment_to_sheet(record)


async def process_pay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик нажатий пользователем кнопки "Оплачено"
    """

    try:
        response_list = update.callback_query.data.split("_")
        approval_id = response_list[1]

    except Exception as e:
        raise RuntimeError(f'Ошибка считывания данных с кнопки "Оплачено". Ошибка: {e}')

    async with db:
        record = await db.get_row_by_id(approval_id)

        if not record:
            raise RuntimeError(f"Запись {approval_id} для оплаты не найдена в таблице")

    async with db:
        await db.update_row_by_id(approval_id, {"status": "Paid"})

    await update.callback_query.edit_message_text(
        text=f"Заявка {approval_id} оплачена.", reply_markup=InlineKeyboardMarkup([])
    )

    # При нажатии "Оплачено" добавляем данные в таблицу
    await add_record_to_google_sheet(record)


async def process_approval(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик нажатий пользователем кнопок "Одобрить" или "Отклонить."
    """

    try:
        response_list = update.callback_query.data.split("_")
        department, action = response_list[1:3]
        approval_id = response_list[3]
        initiator_id = response_list[4]
        approved_user = "@" + update.callback_query.from_user.username

        async with db:
            record = await db.get_row_by_id(approval_id)
            if not record:
                raise RuntimeError("Запись в таблице с данным id не найдена.")

            approved_users_in_db = record["approved_by"]
            if approved_users_in_db:
                approved_users = f"{approved_users_in_db}, {approved_user}"
            else:
                approved_users = approved_user

    except Exception as e:
        raise RuntimeError(f'Ошибка обработки кнопок "Одобрить" и "Отклонить". Ошибка: {e}')

    await handle_head_approval(
        context,
        approval_id,
        initiator_id,
        approved_users,
        record,
        department,
        action,
        update=update,
    )


async def handle_head_approval(
        context,
        approval_id,
        initiator_id,
        approved_users,
        record,
        department,
        action,
        update: Update,
) -> None:
    """Обработчик заявок для одобрения или отклонения."""

    if action == "reject":
        await reject_payment(
            context,
            approval_id,
            initiator_id,
            approved_users,
            department,
            update=update,
        )

    elif action == "approve":
        await approve_payment(
            context,
            approval_id,
            initiator_id,
            approved_users,
            record,
            department,
            update=update,
        )


async def reject_payment(
        context, approval_id, initiator_id, approved_users, department, update: Update
) -> None:
    """Отправка сообщения об отклонении платежа и изменение статуса платежа."""

    if department == "finance":
        approved_by = approved_users.split(", ")
        async with db:
            await db.update_row_by_id(
                approval_id,
                {
                    "approvals_received": 1,
                    "status": "Rejected",
                },
            )
        await update.callback_query.edit_message_text(
            text=f"Заявка {approval_id} отклонена.",
            reply_markup=InlineKeyboardMarkup([]),
        )

        await context.bot.send_message(
            initiator_id, f"Заявка {approval_id} отклонена {approved_by[1]}."
        )

    else:

        async with db:
            await db.update_row_by_id(
                approval_id, {"approvals_received": 0, "status": "Rejected"}
            )

        await update.callback_query.edit_message_text(
            text=f"Заявка {approval_id} отклонена руководителем департамента.",
            reply_markup=InlineKeyboardMarkup([]),
        )

        await context.bot.send_message(
            initiator_id, f"Заявка {approval_id} отклонена {approved_users}."
        )


async def approve_payment(
        context,
        approval_id,
        initiator_id,
        approved_users,
        record,
        department,
        update: Update,
):
    """
    Функция выполняет одну из трёх команд в зависимости от входных данных:
    1)отправка сообщения в финансовый отдел на согласование платежа, если платёж более 50000, меняет количество апрувов
     и статус платежа;
    2)отправка сообщения об одобрении платежа для главы департамента, если платёж менее 50000, меняет количество
     апрувов и статус платежа;
    3)отправка сообщения об одобрении платежа для финансового отдела, меняет количество апрувов и статус платежа.
    """

    if department == "head":
        if float(record["amount"]) >= 50000:

            async with db:
                await db.update_row_by_id(
                    approval_id,
                    {
                        "approvals_received": 1,
                        "status": "Pending",
                        "approved_by": approved_users,
                    },
                )
                record = await db.get_row_by_id(approval_id)

            await update.callback_query.edit_message_text(
                text="Запрос на одобрение отправлен в финансовый " "отдел.",
                reply_markup=InlineKeyboardMarkup([]),
            )
            await create_and_send_approval_message(
                approval_id, initiator_id, record, "finance", context=context
            )

        else:

            async with db:
                await db.update_row_by_id(
                    approval_id,
                    {
                        "approvals_received": 1,
                        "status": "Approved",
                        "approved_by": approved_users,
                    },
                )

                record = await db.get_row_by_id(approval_id)

            await update.callback_query.edit_message_text(
                text="Запрос на платеж одобрен. Заявка готова к оплате.",
                reply_markup=InlineKeyboardMarkup([]),
            )

            await create_and_send_payment_message(
                approval_id, approved_users, record, context
            )

    elif department == "finance":

        async with db:
            await db.update_row_by_id(
                approval_id,
                {
                    "approvals_received": 2,
                    "status": "Approved",
                    "approved_by": approved_users,
                },
            )

            record = await db.get_row_by_id(approval_id)

        await update.callback_query.edit_message_text(
            text="Запрос на платеж одобрен. Заявка готова к оплате.",
            reply_markup=InlineKeyboardMarkup([]),
        )
        await create_and_send_payment_message(
            approval_id, approved_users, record, context
        )


async def error_callback(update: Update, context: CallbackContext) -> None:
    """Обработчик ошибок для логирования и уведомления пользователя с детальной информацией об ошибке."""

    error_text = str(context.error)
    logger.error(f"{error_text}")
    message_text = f'{error_text}'
    if update:
        try:
            chat_ids = [update.effective_chat.id, Config.developer_chat_id]
            await send_message_to_chats(chat_ids=chat_ids, text=message_text, context=context)
            return

        except Exception as e:
            text = f"Ошибка при отправке уведомления об ошибке: {e}."
            logger.error(text)
            return


async def show_not_paid(update: Update) -> None:
    """
    Возвращает все неоплаченные заявки на платежи из таблицы "approvals"
    """

    async with db:
        rows = await db.find_not_paid()
    messages = []

    for i, record in enumerate(rows, start=1):
        line = ", ".join([f"{key}: {value}" for key, value in record.items()])
        message_line = f"{i}. {line}"
        wrapped_message = textwrap.fill(message_line, width=4096)
        messages.append(wrapped_message)

    final_text = "\n\n".join(messages)

    if final_text:
        await update.message.reply_text(final_text)
    else:
        await update.message.reply_text("Заявок не обнаружено")

    return
