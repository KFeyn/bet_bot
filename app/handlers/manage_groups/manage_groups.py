from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command, StateFilter

from app.dbworker import PostgresConnection
from app.utils import generate_manage_groups_keyboard
from app.handlers.manage_groups.create_groups import register_handlers_create_groups, choose_competition
from app.handlers.manage_groups.delete_groups import register_handlers_delete_groups, start_deleting_group
from app.handlers.manage_groups.delete_users_from_groups import (register_handlers_delete_users_from_groups,
                                                                 start_deleting_user_from_group)
from app.handlers.manage_groups.states import ManageGroupsMenu


async def show_manage_groups_menu(message: types.Message, state: FSMContext):
    await state.clear()

    msg = await message.answer("Choose an action:", reply_markup=generate_manage_groups_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await state.set_state(ManageGroupsMenu.waiting_for_action_choice)


async def handle_manage_groups_choice(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    await state.update_data(previous_message_id=call.message.message_id)

    action = call.data.split('_')[1]
    if action == "creategroup":
        await choose_competition(call, state)
    elif action == "deletegroup":
        await start_deleting_group(call, state, pg_con)
    elif action == "deleteuserfromgroup":
        await start_deleting_user_from_group(call, state, pg_con)


def register_handlers_manage_groups(router: Router, pg_con: PostgresConnection):
    async def handle_manage_groups_choice_wrapper(call: types.CallbackQuery, state: FSMContext):
        await handle_manage_groups_choice(call, state, pg_con)

    router.message.register(show_manage_groups_menu, Command("manage_groups"), StateFilter("*"))
    router.callback_query.register(handle_manage_groups_choice_wrapper,
                                   F.data.startswith('manage_'),
                                   StateFilter(ManageGroupsMenu.waiting_for_action_choice))

    register_handlers_create_groups(router, pg_con)
    register_handlers_delete_groups(router, pg_con)
    register_handlers_delete_users_from_groups(router, pg_con)
