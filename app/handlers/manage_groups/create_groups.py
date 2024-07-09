from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.deep_linking import create_start_link
from aiogram.filters import StateFilter
import random
import asyncpg

from app.dbworker import PostgresConnection
from app.utilities import logger, generate_competition_keyboard, generate_id, is_integer
from app.model import Competition


class OrderCreateGroup(StatesGroup):
    waiting_for_comp_picking = State()
    waiting_for_money_picking = State()


class ManageGroupsMenu(StatesGroup):
    waiting_for_action_choice = State()


async def check_groups(pg_con: PostgresConnection, user_id: int) -> bool:
    query = f"""
    select
            count(*) as cnt
    from 
            bets.groups_in_competitions
    where
            added_by = {user_id}
    """
    nums = await pg_con.get_data(query)

    return int(nums[0]['cnt']) <= 2


async def choose_competition(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])

    msg = await call.message.answer("Please choose a competition:", reply_markup=generate_competition_keyboard())
    await state.update_data(previous_message_id=msg.message_id, asking_user_id=str(msg.chat.id))
    await state.set_state(OrderCreateGroup.waiting_for_comp_picking)


async def choose_money(call: types.CallbackQuery, state: FSMContext):
    competition_name = call.data.split('_')[1]

    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    msg = await call.message.answer("Type amount of money:")
    await state.update_data(previous_message_id=msg.message_id, competition_name=competition_name)
    await state.set_state(OrderCreateGroup.waiting_for_money_picking)


async def create_invite_link(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    money = message.text
    if is_integer(money):
        user_data = await state.get_data()
        await message.bot.delete_message(message.chat.id, user_data['previous_message_id'])
        competition_name = user_data['competition_name']
        user_id = int(user_data['asking_user_id'])

        if not await check_groups(pg_con, user_id):
            await message.answer('You reached the limit of three groups!')
            return

        competition = Competition.from_message((competition_name,))
        await competition.check_existing(pg_con)

        group_name = f'{competition.name} group {random.randint(0, 10 ** 12)}'
        link = await create_start_link(bot=message.bot, payload=group_name + '_' + str(user_id), encode=True)

        try:
            await pg_con.insert_data('bets.groups',
                                     ['name'],
                                     [(group_name,)])
            await pg_con.insert_data('bets.groups_in_competitions',
                                     ['group_id', 'competition_id', 'added_by', 'money', 'invite_link'],
                                     [(generate_id(group_name), competition.id, user_id, money, link)])
            await pg_con.insert_data('bets.users_in_groups',
                                     ['user_id', 'group_id', 'added_by', 'is_admin'],
                                     [(user_id, generate_id(group_name), user_id, True)])
        except asyncpg.exceptions.UniqueViolationError:
            await message.answer('We got a double, please retry')
            logger.error('We have got a UniqueViolationError when creating group')
            await state.clear()
            return
        except asyncpg.exceptions.PostgresError as e:
            await message.answer('We got a bug, please write to @sartrsmotritkrivo')
            logger.error(f'We have got an unexpected error {e}')
            await state.clear()
            return

        await message.answer(f"Invite link created:\n```{link}```\nSend it to users you want to add to this group",
                             parse_mode='MARKDOWN')
        await state.clear()
        logger.info(f'User {user_id} created group {generate_id(group_name)} in competition {competition.id}')
    else:
        await message.reply('It is not a number, please type the correct number')
        await state.set_state(OrderCreateGroup.waiting_for_money_picking)


def register_handlers_create_groups(router: Router, pg_con: PostgresConnection):
    async def create_invite_link_wrapper(message: types.Message, state: FSMContext):
        await create_invite_link(message, state, pg_con)

    router.callback_query.register(choose_competition, StateFilter(ManageGroupsMenu.waiting_for_action_choice))
    router.callback_query.register(choose_money, F.data.startswith('comps_'),
                                   StateFilter(OrderCreateGroup.waiting_for_comp_picking))
    router.message.register(create_invite_link_wrapper, StateFilter(OrderCreateGroup.waiting_for_money_picking))
