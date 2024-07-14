import asyncpg
import random

from aiogram import Router, types, F
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.deep_linking import create_start_link

from app.dbworker import PostgresConnection
from app.models import Competition
from app.utils import generate_competition_keyboard, generate_starting_stage_keyboard, generate_id, is_integer, logger
from app.handlers.manage_groups.states import OrderCreateGroup, ManageGroupsMenu


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


async def choose_start_stage(call: types.CallbackQuery, state: FSMContext):
    competition_name = call.data.split('_')[1]

    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])

    msg = await call.message.answer("Please choose from which state you will start betting:",
                                    reply_markup=generate_starting_stage_keyboard())
    await state.update_data(previous_message_id=msg.message_id, competition_name=competition_name)
    await state.set_state(OrderCreateGroup.waiting_for_start_stage_picking)


async def choose_money(call: types.CallbackQuery, state: FSMContext):
    start_stage = call.data.split('_')[1]

    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    msg = await call.message.answer("Type amount of money:")
    await state.update_data(previous_message_id=msg.message_id, start_stage=start_stage)
    await state.set_state(OrderCreateGroup.waiting_for_money_entering)


async def create_invite_link(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    money = message.text
    user_data = await state.get_data()

    if is_integer(money):
        await message.bot.delete_message(message.chat.id, user_data['previous_message_id'])
        competition_name = user_data['competition_name']
        user_id = int(user_data['asking_user_id'])
        start_stage = user_data['start_stage']

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
                                     ['group_id', 'competition_id', 'added_by', 'money', 'invite_link', 'starting_stage'],
                                     [(generate_id(group_name), competition.id, user_id, money, link, start_stage)])
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
        tries = int(user_data.get('tries', 0)) + 1
        if tries > 2:
            await message.reply('You are mistaken 3 times, exiting from preparing groups')
            await state.clear()
            return
        await state.update_data(tries=tries)
        await state.set_state(OrderCreateGroup.waiting_for_money_entering)


def register_handlers_create_groups(router: Router, pg_con: PostgresConnection):
    async def create_invite_link_wrapper(message: types.Message, state: FSMContext):
        await create_invite_link(message, state, pg_con)

    router.callback_query.register(choose_competition, StateFilter(ManageGroupsMenu.waiting_for_action_choice))
    router.callback_query.register(choose_start_stage, F.data.startswith('comps_'),
                                   StateFilter(OrderCreateGroup.waiting_for_comp_picking))
    router.callback_query.register(choose_money, F.data.startswith('startstage_'),
                                   StateFilter(OrderCreateGroup.waiting_for_start_stage_picking))
    router.message.register(create_invite_link_wrapper, StateFilter(OrderCreateGroup.waiting_for_money_entering))
