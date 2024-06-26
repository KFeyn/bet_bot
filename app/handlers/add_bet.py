import logging
import typing as tp
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from ..dbworker import PostgresConnection


class OrderPlaceBets(StatesGroup):
    waiting_for_comp_and_group_picking = State()
    waiting_for_match_picking = State()
    waiting_for_first_team_goals = State()
    waiting_for_second_team_goals = State()
    waiting_for_penalty_winner = State()


def generate_number_keyboard():
    keyboard = types.InlineKeyboardMarkup()
    for i in range(11):
        keyboard.add(types.InlineKeyboardButton(text=str(i), callback_data=f'goals_{i}'))
    return keyboard


def generate_teams_keyboard(first_team_name: str, second_team_name: str):
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text=first_team_name, callback_data='penalty_1'))
    keyboard.add(types.InlineKeyboardButton(text=second_team_name, callback_data='penalty_2'))
    return keyboard


async def start_placing_a_bet(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    await state.finish()

    query_get = f"""
    select 
            comp.name || ' - ' || grp.name  as c_g_pair
            ,comp.id as competition_id
            ,grp.id as group_id
    from 
            bets.users_in_groups as uig
    join 
            bets.groups as grp
                on grp.id = uig.group_id
    join 
            bets.groups_in_competitions as gic
                    on uig.group_id = gic.group_id
    join
            bets.competitions as comp
                    on comp.id = gic.competition_id
                    and comp.start_date - now() > interval '24 hours'
    where 
            uig.user_id = ('x'||left(md5('{message.from_user.username}'), 16))::BIT(64)::BIGINT 
    """
    comps = await pg_con.get_data(query_get)

    if len(comps) == 0:
        await message.answer("You don't participate in any competition!")

    elif len(comps) > 1:

        keyboard = types.InlineKeyboardMarkup()
        for comp in comps:
            keyboard.add(types.InlineKeyboardButton(text=comp['c_g_pair'],
                                                    callback_data=f"competitions_{comp['c_g_pair']}_{comp['competition_id']}_{comp['group_id']}"))
        msg = await message.answer("Please choose a competition qand group pair:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id)
        await OrderPlaceBets.waiting_for_comp_and_group_picking.set()

    else:
        await start_picking_match(message, state, pg_con)


async def start_picking_match(message: types.Message, state: FSMContext, pg_con: PostgresConnection):

    query_get = f"""
    select 
            first_team || ' - ' || second_team as pair
            ,id
            ,('x'||left(md5('{message.from_user.username}'), 16))::BIT(64)::BIGINT as user_id
    from 
            bets.matches 
    where
            not exists (select 1 from bets.bets where bets.matches.id = bets.bets.match_id
            and bets.bets.user_id = ('x'||left(md5('{message.from_user.username}'), 16))::BIT(64)::BIGINT 
            )
            and dt - now() > interval '24 hours' 
            
    """
    teams = await pg_con.get_data(query_get)

    keyboard = types.InlineKeyboardMarkup()
    for team in teams:
        keyboard.add(types.InlineKeyboardButton(text=team['pair'],
                                                callback_data=f"match_{team['id']}_{team['pair']}_{team['user_id']}"))
    msg = await message.answer("Please choose a match:", reply_markup=keyboard)
    await state.update_data(previous_message_id=msg.message_id)
    await OrderPlaceBets.waiting_for_match_picking.set()


async def start_changing_a_bet(message: types.Message, state: FSMContext, pg_con: PostgresConnection):
    await state.finish()

    query_get = f"""
    select q
            first_team || ' - ' || second_team as pair
            ,id
            ,('x'||left(md5('{message.from_user.username}'), 16))::BIT(64)::BIGINT as user_id
    from 
            bets.matches 
    where
            exists (select 1 from bets.bets where bets.matches.id = bets.bets.match_id
            and bets.bets.user_id = ('x'||left(md5('{message.from_user.username}'), 16))::BIT(64)::BIGINT )
            and dt - now() > interval '24 hours' 
            
    """
    teams = await pg_con.get_data(query_get)

    keyboard = types.InlineKeyboardMarkup()
    for team in teams:
        keyboard.add(types.InlineKeyboardButton(text=team['pair'],
                                                callback_data=f"change_{team['id']}_{team['pair']}_{team['user_id']}"))
    msg = await message.answer("Please choose a match:", reply_markup=keyboard)
    await state.update_data(previous_message_id=msg.message_id)
    await OrderPlaceBets.waiting_for_match_picking.set()


async def match_picked(call: types.CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    match_id, pair, user_id = call.data.split('_')[1], call.data.split('_')[2], call.data.split('_')[3]
    await state.update_data(match_id=match_id, pair=pair, user_id=user_id)
    msg = await call.message.answer("Please enter the goals for the first team:",
                                    reply_markup=generate_number_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderPlaceBets.waiting_for_first_team_goals.set()


async def first_team_goals_entered(call: types.CallbackQuery, state: FSMContext):
    first_team_goals = int(call.data.split('_')[1])
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(first_team_goals=first_team_goals)
    msg = await call.message.answer("Please enter the goals for the second team:",
                                    reply_markup=generate_number_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await OrderPlaceBets.waiting_for_second_team_goals.set()


async def second_team_goals_entered(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    second_team_goals = int(call.data.split('_')[1])
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(second_team_goals=second_team_goals)
    first_team_name, second_team_name = user_data['pair'].split(' - ')

    if user_data['first_team_goals'] == second_team_goals:
        msg = await call.message.answer("The scores are equal. Please choose the penalty winner:",
                                        reply_markup=generate_teams_keyboard(first_team_name, second_team_name))
        await state.update_data(previous_message_id=msg.message_id)
        await OrderPlaceBets.waiting_for_penalty_winner.set()
    else:
        await state.update_data(is_penalty=False, penalty_winner=0)
        await save_bet(call, state, pg_con)


async def penalty_winner_entered(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    penalty_winner = int(call.data.split('_')[1])
    await state.update_data(is_penalty=True, penalty_winner=penalty_winner)
    await save_bet(call, state, pg_con)


async def save_bet(call: types.CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await pg_con.insert_data('bets.bets',
                             ['match_id', 'user_id', 'first_team_goals', 'second_team_goals', 'is_penalty',
                              'penalty_winner'],
                             [(user_data['match_id'], user_data['user_id'], user_data['first_team_goals'],
                               user_data['second_team_goals'], user_data['is_penalty'], user_data['penalty_winner'])])

    await call.message.answer("Your bet has been placed successfully!", reply_markup=types.ReplyKeyboardRemove())
    logging.info(f'Bet for match {user_data["match_id"]} for user {user_data["user_id"]} is written successfuly')
    await state.finish()


def register_handlers_add_bet(dp: Dispatcher, pg_con: PostgresConnection):
    async def start_placing_a_bet_wrapper(message: types.Message, state: FSMContext):
        await start_placing_a_bet(message, state, pg_con)

    async def start_changing_a_bet_wrapper(message: types.Message, state: FSMContext):
        await start_changing_a_bet(message, state, pg_con)

    async def penalty_winner_entered_wrapper(call: types.CallbackQuery, state: FSMContext):
        await penalty_winner_entered(call, state, pg_con)

    async def second_team_goals_entered_wrapper(call: types.CallbackQuery, state: FSMContext):
        await second_team_goals_entered(call, state, pg_con)

    dp.register_message_handler(start_placing_a_bet_wrapper, commands="add_bet", state="*")
    dp.register_message_handler(start_changing_a_bet_wrapper, commands="change_bet", state="*")
    dp.register_callback_query_handler(match_picked, lambda call: call.data.startswith('match_') or
                                                                  call.data.startswith('change_'),
                                       state=OrderPlaceBets.waiting_for_match_picking)
    dp.register_callback_query_handler(first_team_goals_entered, lambda call: call.data.startswith('goals_'),
                                       state=OrderPlaceBets.waiting_for_first_team_goals)
    dp.register_callback_query_handler(second_team_goals_entered_wrapper, lambda call: call.data.startswith('goals_'),
                                       state=OrderPlaceBets.waiting_for_second_team_goals)
    dp.register_callback_query_handler(penalty_winner_entered_wrapper, lambda call: call.data.startswith('penalty_'),
                                       state=OrderPlaceBets.waiting_for_penalty_winner)
