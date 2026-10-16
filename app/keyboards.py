from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton,
)


def kb_role():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍👩‍👧 Родственник", callback_data="role:family")],
        [InlineKeyboardButton(text="❤️ Близкий", callback_data="role:elderly")],
    ])


def kb_consent():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Согласен", callback_data="consent:yes")],
        [InlineKeyboardButton(text="Отказаться", callback_data="consent:no")],
    ])


def kb_family_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="👨‍👩‍👧 Моя семья"), KeyboardButton(text="⚙️ Аккаунт")],
        [KeyboardButton(text="📊 Отчёты"), KeyboardButton(text="📨 История обращений")],
        [KeyboardButton(text="✉️ Отправить сообщение близкому")],
        [KeyboardButton(text="🛠 Написать в техподдержку"), KeyboardButton(text="❓ Как пользоваться ботом?")],
    ], resize_keyboard=True)


def kb_elderly_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="☀️ Я проснулся")],
        [KeyboardButton(text="😊 Как я себя чувствую"), KeyboardButton(text="🩺 Сообщить о проблеме")],
        [KeyboardButton(text="📋 Мои задачи")],
        [KeyboardButton(text="✉️ Отправить сообщение родственнику")],
        [KeyboardButton(text="❓ Как пользоваться ботом?")],
    ], resize_keyboard=True)


def kb_family_root():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Семья (родственники)", callback_data="fam:relatives")],
        [InlineKeyboardButton(text="❤️ Близкие (под нашей заботой)", callback_data="fam:elderly")],
    ])


def kb_relatives_panel(members: list, owner_user_id: int, my_user_id: int):
    rows = []
    for u, r in members:
        if r == "owner":
            label = "👑 " + u.name
        elif r == "moderator":
            label = "🔧 " + u.name
        else:
            label = "• " + u.name
        line = [InlineKeyboardButton(text=label, callback_data="noop")]
        if my_user_id == owner_user_id and r != "owner":
            if r == "moderator":
                line.append(InlineKeyboardButton(
                    text="Снять 🔧",
                    callback_data="demote:" + str(u.id),
                ))
            else:
                line.append(InlineKeyboardButton(
                    text="🔧",
                    callback_data="promote:" + str(u.id),
                ))
            line.append(InlineKeyboardButton(
                text="🗑",
                callback_data="del_member:" + str(u.id),
            ))
        rows.append(line)
    if my_user_id == owner_user_id:
        rows.append([InlineKeyboardButton(
            text="➕ Пригласить родственника",
            callback_data="invite_member",
        )])
    rows.append([InlineKeyboardButton(
        text="🚪 Выйти из семьи",
        callback_data="leave_family",
    )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="fam:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_elderly_panel(elderly_list: list):
    rows = []
    for e in elderly_list:
        if e.user_id:
            mark = "✅"
        else:
            mark = "⏳"
        rows.append([InlineKeyboardButton(
            text=mark + " " + e.name,
            callback_data="eld:" + str(e.id),
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить близкого",
                                      callback_data="add_elderly")])
    rows.append([InlineKeyboardButton(text="🎁 Шаблоны распорядка",
                                      callback_data="tpl_choose")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="fam:root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_choose_elderly(elderly_list: list, prefix: str):
    rows = []
    for e in elderly_list:
        rows.append([InlineKeyboardButton(
            text=e.name,
            callback_data=prefix + ":" + str(e.id),
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="fam:elderly")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_recipient_pick(items: list, prefix: str,
                      all_label: str = None, all_callback: str = None,
                      cancel_callback: str = "pick_cancel"):
    rows = []
    if all_label and all_callback:
        rows.append([InlineKeyboardButton(text=all_label,
                                          callback_data=all_callback)])
    for it in items:
        rows.append([InlineKeyboardButton(
            text=it.name,
            callback_data=prefix + ":" + str(it.id),
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Отмена",
                                      callback_data=cancel_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_problem_pick():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤕 Болит голова", callback_data="prob:head"),
         InlineKeyboardButton(text="🫀 Болит сердце", callback_data="prob:heart")],
        [InlineKeyboardButton(text="😮‍💨 Тяжело дышать", callback_data="prob:breath"),
         InlineKeyboardButton(text="🤢 Тошнит", callback_data="prob:nausea")],
        [InlineKeyboardButton(text="💫 Головокружение", callback_data="prob:dizzy"),
         InlineKeyboardButton(text="🤍 Болит живот", callback_data="prob:stomach")],
        [InlineKeyboardButton(text="🥱 Слабость", callback_data="prob:weak"),
         InlineKeyboardButton(text="📝 Другое", callback_data="prob:other")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="prob:cancel")],
    ])


def kb_elderly_manage(elderly_id: int, can_edit: bool, is_owner: bool):
    rows = [
        [InlineKeyboardButton(text="📋 Распорядок",
                              callback_data="rt_menu:" + str(elderly_id))],
        [InlineKeyboardButton(text="📝 Заметки",
                              callback_data="notes:" + str(elderly_id))],
    ]
    if can_edit:
        rows.append([InlineKeyboardButton(text="🎁 Шаблоны",
                                          callback_data="tpl:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="⏰ Время чек-ина",
                                          callback_data="checkin:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="🌙 Тихие часы",
                                          callback_data="quiet:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="🎂 День рождения",
                                          callback_data="bday:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="🔗 Ссылка для близкого",
                                          callback_data="invite_eld:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="📤 Экспорт истории",
                                          callback_data="csv:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="⏸ Пауза / ▶️ Возобновить",
                                          callback_data="toggle:" + str(elderly_id))])
    if is_owner:
        rows.append([InlineKeyboardButton(text="🗑 Удалить близкого",
                                          callback_data="del_eld:" + str(elderly_id))])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="fam:elderly")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_quiet_panel(elderly_id: int, enabled: bool, start: int, end: int,
                   is_quiet_now: bool):
    if enabled:
        toggle_label = "🔕 Отключить тихие часы"
    else:
        toggle_label = "🔔 Включить тихие часы"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=toggle_label,
                              callback_data="quiet_toggle:" + str(elderly_id))],
        [InlineKeyboardButton(text="⏰ Изменить время",
                              callback_data="quiet_time:" + str(elderly_id))],
        [InlineKeyboardButton(text="⬅️ Назад",
                              callback_data="eld:" + str(elderly_id))],
    ])


def kb_birthday_panel(elderly_id: int, current):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Задать / изменить",
                              callback_data="bday_set:" + str(elderly_id))],
        [InlineKeyboardButton(text="🗑 Убрать",
                              callback_data="bday_clear:" + str(elderly_id))],
        [InlineKeyboardButton(text="⬅️ Назад",
                              callback_data="eld:" + str(elderly_id))],
    ])


def kb_measure_kind_pick(elderly_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🩺 Давление",
            callback_data="rt_measure_kind:" + str(elderly_id) + ":pressure",
        )],
        [InlineKeyboardButton(
            text="🍬 Сахар",
            callback_data="rt_measure_kind:" + str(elderly_id) + ":sugar",
        )],
        [InlineKeyboardButton(
            text="⚖️ Вес",
            callback_data="rt_measure_kind:" + str(elderly_id) + ":weight",
        )],
        [InlineKeyboardButton(
            text="💓 Пульс",
            callback_data="rt_measure_kind:" + str(elderly_id) + ":pulse",
        )],
        [InlineKeyboardButton(
            text="⬅️ Отмена",
            callback_data="rt_menu:" + str(elderly_id),
        )],
    ])


def kb_routine_menu(elderly_id: int, routines: list, can_edit: bool = True):
    rows = []
    for r in routines:
        if r.mode == "wake_offset":
            when = "через " + str(r.offset_min) + " мин"
        else:
            when = f"{r.hour:02d}:{r.minute:02d}"
        prefix = "🩺 " if r.measure_kind else "✏️ "
        label = prefix + r.title + " (" + when + ")"
        if can_edit:
            rows.append([InlineKeyboardButton(
                text=label, callback_data="rt_edit:" + str(r.id),
            )])
        else:
            rows.append([InlineKeyboardButton(text=label, callback_data="noop")])
    if can_edit:
        rows.append([InlineKeyboardButton(text="➕ Добавить задачу",
                                          callback_data="rt_add:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="🩺 Добавить замер",
                                          callback_data="rt_add_measure:" + str(elderly_id))])
        rows.append([InlineKeyboardButton(text="🎁 Применить шаблон",
                                          callback_data="tpl:" + str(elderly_id))])
        if routines:
            rows.append([InlineKeyboardButton(text="🗑 Очистить распорядок",
                                              callback_data="rt_clear:" + str(elderly_id))])
    rows.append([InlineKeyboardButton(text="⬅️ Назад",
                                      callback_data="eld:" + str(elderly_id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_clear_confirm(elderly_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить всё",
                              callback_data="rt_clear_yes:" + str(elderly_id))],
        [InlineKeyboardButton(text="⬅️ Отмена",
                              callback_data="rt_menu:" + str(elderly_id))],
    ])


def kb_routine_edit(routine_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Изменить название",
                              callback_data="rt_rename:" + str(routine_id))],
        [InlineKeyboardButton(text="⏰ Изменить время",
                              callback_data="rt_retime:" + str(routine_id))],
        [InlineKeyboardButton(text="🗑 Удалить",
                              callback_data="rt_del:" + str(routine_id))],
        [InlineKeyboardButton(text="⬅️ Назад",
                              callback_data="rt_back:" + str(routine_id))],
    ])


def kb_templates(elderly_id: int, has_routines: bool = False):
    rows = [
        [InlineKeyboardButton(text="Базовый уход",
                              callback_data="tpl_apply:" + str(elderly_id) + ":basic")],
        [InlineKeyboardButton(text="Активный день",
                              callback_data="tpl_apply:" + str(elderly_id) + ":active")],
        [InlineKeyboardButton(text="Минимальный",
                              callback_data="tpl_apply:" + str(elderly_id) + ":minimal")],
        [InlineKeyboardButton(text="🩺 Гипертония (давление)",
                              callback_data="tpl_apply:" + str(elderly_id) + ":hypertonia")],
        [InlineKeyboardButton(text="🍬 Диабет (сахар)",
                              callback_data="tpl_apply:" + str(elderly_id) + ":diabetes")],
        [InlineKeyboardButton(text="🩺🍬 Полный (давление и сахар)",
                              callback_data="tpl_apply:" + str(elderly_id) + ":full_care")],
        [InlineKeyboardButton(text="📂 Мои шаблоны",
                              callback_data="tpl_my:" + str(elderly_id))],
    ]
    if has_routines:
        rows.append([InlineKeyboardButton(
            text="💾 Сохранить текущий как шаблон",
            callback_data="tpl_save:" + str(elderly_id),
        )])
    rows.append([InlineKeyboardButton(
        text="📄 Загрузить выписку врача (AI)",
        callback_data="tpl_ai:" + str(elderly_id),
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="rt_menu:" + str(elderly_id),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_template_apply_mode(elderly_id: int, key: str, has_routines: bool):
    rows = [
        [InlineKeyboardButton(
            text="✅ Применить (заменить всё)",
            callback_data="tpl_mode:" + str(elderly_id) + ":" + key + ":replace",
        )],
    ]
    if has_routines:
        rows.append([InlineKeyboardButton(
            text="➕ Добавить к текущим",
            callback_data="tpl_mode:" + str(elderly_id) + ":" + key + ":append",
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Отмена",
        callback_data="tpl:" + str(elderly_id),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_custom_templates(elderly_id: int, templates: list):
    rows = []
    for t in templates:
        rows.append([InlineKeyboardButton(
            text="📋 " + t.name,
            callback_data="tpl_custom_apply:" + str(t.id) + ":" + str(elderly_id),
        )])
        rows.append([InlineKeyboardButton(
            text="🗑 Удалить: " + t.name[:25],
            callback_data="tpl_custom_del:" + str(t.id) + ":" + str(elderly_id),
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад",
        callback_data="tpl:" + str(elderly_id),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_custom_template_apply(tid: int, elderly_id: int, has_routines: bool):
    rows = [
        [InlineKeyboardButton(
            text="✅ Применить (заменить всё)",
            callback_data="tpl_custom_mode:" + str(tid) + ":" + str(elderly_id) + ":replace",
        )],
    ]
    if has_routines:
        rows.append([InlineKeyboardButton(
            text="➕ Добавить к текущим",
            callback_data="tpl_custom_mode:" + str(tid) + ":" + str(elderly_id) + ":append",
        )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Отмена",
        callback_data="tpl_my:" + str(elderly_id),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_routine_event(event_id: int, is_measure: bool = False):
    if is_measure:
        done_text = "✍️ Ввести значение"
    else:
        done_text = "✅ Сделано"
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=done_text,
                                 callback_data="rt:done:" + str(event_id)),
            InlineKeyboardButton(text="Пропустил",
                                 callback_data="rt:skip:" + str(event_id)),
        ],
        [InlineKeyboardButton(text="🕒 Позже",
                              callback_data="rt:later:" + str(event_id))],
        [InlineKeyboardButton(text="📞 Позвонить близким",
                              callback_data="rt:call:" + str(event_id))],
    ])


def kb_wake():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Я проснулся", callback_data="woke_up")],
    ])


def kb_wellbeing():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Хорошо", callback_data="wb:good")],
        [InlineKeyboardButton(text="Так себе", callback_data="wb:ok")],
        [InlineKeyboardButton(text="Плохо", callback_data="wb:bad")],
        [InlineKeyboardButton(text="Нужна помощь", callback_data="wb:help")],
    ])


def kb_help_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить", callback_data="help:send")],
        [InlineKeyboardButton(text="❌ Отменить", callback_data="help:cancel")],
    ])


def kb_account_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚪 Выйти из семьи",
                              callback_data="leave_family")],
        [InlineKeyboardButton(text="🔕 Пауза в уведомлениях",
                              callback_data="mute_panel")],
        [InlineKeyboardButton(text="🗑 Удалить аккаунт",
                              callback_data="acc:delete_confirm")],
    ])


def kb_account_delete_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, удалить всё",
                              callback_data="acc:delete_yes")],
        [InlineKeyboardButton(text="⬅️ Отмена", callback_data="acc:cancel")],
    ])


def kb_admin():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Сводка", callback_data="adm_stats")],
        [InlineKeyboardButton(text="👨‍👩‍👧 Семьи", callback_data="adm_families")],
        [InlineKeyboardButton(text="❤️ Близкие", callback_data="adm_elderly")],
        [InlineKeyboardButton(text="📨 Заявки", callback_data="adm_help")],
        [InlineKeyboardButton(text="💾 Бэкапы", callback_data="adm_backups")],
    ])


def kb_admin_help_list(requests: list):
    rows = []
    for hr in requests:
        mark = "🆕" if hr.status == "new" else "✅"
        preview = hr.request_text[:30].replace("\n", " ")
        if len(hr.request_text) > 30:
            preview = preview + "…"
        rows.append([InlineKeyboardButton(
            text=mark + " #" + str(hr.id) + " " + preview,
            callback_data="adm_hr:" + str(hr.id),
        )])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="adm_back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_admin_help_detail(rid: int, can_reply: bool):
    rows = []
    if can_reply:
        rows.append([InlineKeyboardButton(
            text="✏️ Ответить",
            callback_data="adm_hr_reply:" + str(rid),
        )])
    rows.append([InlineKeyboardButton(text="⬅️ К списку", callback_data="adm_help")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_faq_family():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Начало работы", callback_data="faq:fam:start")],
        [InlineKeyboardButton(text="👨‍👩‍👧 Моя семья", callback_data="faq:fam:family")],
        [InlineKeyboardButton(text="❤️ Добавить близкого", callback_data="faq:fam:add_eld")],
        [InlineKeyboardButton(text="✉️ Пригласить родственника", callback_data="faq:fam:invite")],
        [InlineKeyboardButton(text="🔧 Роли в семье", callback_data="faq:fam:roles")],
        [InlineKeyboardButton(text="📋 Распорядок дня", callback_data="faq:fam:routine")],
        [InlineKeyboardButton(text="➕ Добавить задачу", callback_data="faq:fam:add_task")],
        [InlineKeyboardButton(text="⏰ Время и форматы", callback_data="faq:fam:time")],
        [InlineKeyboardButton(text="🎁 Шаблоны и AI-выписка", callback_data="faq:fam:templates")],
        [InlineKeyboardButton(text="☀️ Пробуждение", callback_data="faq:fam:wake")],
        [InlineKeyboardButton(text="🔔 Уведомления и тревоги", callback_data="faq:fam:alerts")],
        [InlineKeyboardButton(text="🌙 Тихие часы", callback_data="faq:fam:quiet")],
        [InlineKeyboardButton(text="📝 Заметки", callback_data="faq:fam:notes")],
        [InlineKeyboardButton(text="🔕 Пауза в уведомлениях", callback_data="faq:fam:mute")],
        [InlineKeyboardButton(text="📊 Отчёты и аналитика", callback_data="faq:fam:reports")],
        [InlineKeyboardButton(text="📤 Экспорт истории", callback_data="faq:fam:csv")],
        [InlineKeyboardButton(text="✉️ Написать близкому", callback_data="faq:fam:msg_elderly")],
        [InlineKeyboardButton(text="📨 Заявки в техподдержку", callback_data="faq:fam:help")],
        [InlineKeyboardButton(text="⚙️ Аккаунт", callback_data="faq:fam:account")],
        [InlineKeyboardButton(text="🔒 Приватность и 152-ФЗ", callback_data="faq:fam:privacy")],
        [InlineKeyboardButton(text="⬅️ Закрыть", callback_data="faq:close")],
    ])


def kb_faq_elderly():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="☀️ Я проснулся", callback_data="faq:eld:wake")],
        [InlineKeyboardButton(text="📋 Мои задачи", callback_data="faq:eld:tasks")],
        [InlineKeyboardButton(text="✅ Как отметить задачу", callback_data="faq:eld:mark")],
        [InlineKeyboardButton(text="😊 Самочувствие и голосовые", callback_data="faq:eld:wellbeing")],
        [InlineKeyboardButton(text="🩺 Сообщить о проблеме", callback_data="faq:eld:problem")],
        [InlineKeyboardButton(text="✉️ Написать родственнику", callback_data="faq:eld:msg")],
        [InlineKeyboardButton(text="🔔 Что значат уведомления", callback_data="faq:eld:alerts")],
        [InlineKeyboardButton(text="🆘 Что делать в экстренном случае", callback_data="faq:eld:sos")],
        [InlineKeyboardButton(text="⬅️ Закрыть", callback_data="faq:close")],
    ])


def kb_faq_back(is_family: bool):
    if is_family:
        back = "faq:root_fam"
    else:
        back = "faq:root_eld"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ К разделам", callback_data=back)],
    ])


def kb_reports_menu(elderly_list: list):
    rows = [
        [InlineKeyboardButton(text="📈 Прогресс за неделю",
                              callback_data="an:week")],
        [InlineKeyboardButton(text="📋 Семейный лог за сутки",
                              callback_data="an:log")],
    ]
    for e in elderly_list:
        rows.append([InlineKeyboardButton(
            text="📊 Отчёт: " + e.name,
            callback_data="rep_view:" + str(e.id),
        )])
        rows.append([InlineKeyboardButton(
            text="📥 CSV по " + e.name,
            callback_data="rep_csv:" + str(e.id),
        )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_analytics_elderly_pick(elderly_list: list, prefix: str):
    rows = []
    for e in elderly_list:
        rows.append([InlineKeyboardButton(
            text=e.name,
            callback_data=prefix + ":" + str(e.id),
        )])
    rows.append([InlineKeyboardButton(text="⬅️ К отчётам",
                                      callback_data="rep_root")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_report_elderly(elderly_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="📥 Скачать CSV",
            callback_data="rep_csv:" + str(elderly_id),
        )],
        [InlineKeyboardButton(
            text="⬅️ К отчётам",
            callback_data="rep_root",
        )],
    ])


def kb_ai_preview(has_routines: bool):
    rows = [
        [InlineKeyboardButton(
            text="✅ Применить (заменить всё)",
            callback_data="ai_apply:replace",
        )],
    ]
    if has_routines:
        rows.append([InlineKeyboardButton(
            text="➕ Добавить к текущим",
            callback_data="ai_apply:append",
        )])
    rows.append([InlineKeyboardButton(
        text="💾 Применить и сохранить как шаблон",
        callback_data="ai_apply_save",
    )])
    rows.append([InlineKeyboardButton(
        text="❌ Отмена",
        callback_data="ai_cancel",
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_alert_actions(elderly_id: int, kind: str, summary: str = ""):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="✅ Взял на контроль",
            callback_data="ack:" + str(elderly_id) + ":" + kind,
        )],
        [InlineKeyboardButton(
            text="🔕 Тишина на 1 час",
            callback_data="mute:60",
        )],
    ])


def kb_notes_menu(elderly_id: int, notes: list):
    rows = []
    for n in notes:
        when = n.remind_at.strftime("%d.%m %H:%M")
        label = "📝 " + when + " — " + n.text[:30]
        rows.append([InlineKeyboardButton(
            text=label, callback_data="note_view:" + str(n.id),
        )])
    rows.append([InlineKeyboardButton(
        text="➕ Добавить заметку",
        callback_data="note_add:" + str(elderly_id),
    )])
    rows.append([InlineKeyboardButton(
        text="⬅️ Назад", callback_data="eld:" + str(elderly_id),
    )])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_note_view(nid: int, elderly_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🗑 Удалить",
            callback_data="note_del:" + str(nid),
        )],
        [InlineKeyboardButton(
            text="⬅️ К заметкам",
            callback_data="notes:" + str(elderly_id),
        )],
    ])


def kb_note_feedback(nid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Всё хорошо", callback_data="note_fb:" + str(nid) + ":good")],
        [InlineKeyboardButton(text="😐 Так себе", callback_data="note_fb:" + str(nid) + ":meh")],
        [InlineKeyboardButton(text="❌ Не получилось", callback_data="note_fb:" + str(nid) + ":bad")],
    ])


def kb_mute_panel(current_mute=None):
    if current_mute:
        rows = [
            [InlineKeyboardButton(text="▶️ Снять паузу",
                                  callback_data="mute_off")],
        ]
    else:
        rows = [
            [InlineKeyboardButton(text="🔕 1 час", callback_data="mute:60"),
             InlineKeyboardButton(text="🔕 6 часов", callback_data="mute:360")],
            [InlineKeyboardButton(text="🔕 1 день", callback_data="mute:1440"),
             InlineKeyboardButton(text="🔕 3 дня", callback_data="mute:4320")],
            [InlineKeyboardButton(text="🔕 7 дней", callback_data="mute:10080")],
        ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_leave_family_confirm(is_owner: bool, has_others: bool):
    if is_owner and not has_others:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⬅️ Понятно", callback_data="family:back")],
        ])
    if is_owner and has_others:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⚠️ Да, передать владение и выйти",
                                  callback_data="leave_family_yes")],
            [InlineKeyboardButton(text="⬅️ Остаться", callback_data="family:back")],
        ])
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚠️ Да, выйти",
                              callback_data="leave_family_yes")],
        [InlineKeyboardButton(text="⬅️ Остаться", callback_data="family:back")],
    ])