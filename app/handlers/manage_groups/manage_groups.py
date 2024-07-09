from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext

from app.dbworker import PostgresConnection
from app.handlers.manage_groups.create_groups import register_handlers_create_groups, choose_competition
from app.handlers.manage_groups.delete_groups import register_handlers_delete_groups, start_deleting_group
from app.handlers.manage_groups.delete_users_from_groups import (register_handlers_delete_users_from_groups,
                                                                 start_deleting_user_from_group)
from app.handlers.manage_groups.states import ManageGroupsMenu


async def show_manage_groups_menu(message: types.Message, state: FSMContext):
    await state.finish()

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="Create Group", callback_data="manage_creategroup"))
    keyboard.add(types.InlineKeyboardButton(text="Delete Group", callback_data="manage_deletegroup"))
    keyboard.add(types.InlineKeyboardButton(text="Delete User from Group", callback_data="manage_deleteuserfromgroup"))

    await message.answer("Choose an action:", reply_markup=keyboard)
    await ManageGroupsMenu.waiting_for_action_choice.set()


async def handle_manage_groups_choice(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):

    await state.update_data(previous_message_id=call.message.message_id)

    action = call.data.split('_')[1]
    if action == "creategroup":
        await choose_competition(call, state)
    elif action == "deletegroup":
        await start_deleting_group(call, state, pg_con)
    elif action == "deleteuserfromgroup":
        await start_deleting_user_from_group(call, state, pg_con)


def register_handlers_manage_groups(dp: Dispatcher, pg_con: PostgresConnection):
    async def handle_manage_groups_choice_wrapper(call: types.CallbackQuery, state: FSMContext):
        await handle_manage_groups_choice(call, state, pg_con)

    dp.register_message_handler(show_manage_groups_menu, commands="manage_groups", state="*")
    dp.register_callback_query_handler(handle_manage_groups_choice_wrapper,
                                       lambda call: call.data.startswith('manage_'),
                                       state=ManageGroupsMenu.waiting_for_action_choice)

    # Register handlers from other files
    register_handlers_create_groups(dp, pg_con)
    register_handlers_delete_groups(dp, pg_con)
    register_handlers_delete_users_from_groups(dp, pg_con)
