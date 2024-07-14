from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import Command, StateFilter

from app.dbworker import PostgresConnection
from app.utils import logger, generate_teams_keyboard, generate_number_keyboard


class OrderPlaceBets(StatesGroup):
    waiting_for_comp_and_group_picking = State()
    waiting_for_match_picking = State()
    waiting_for_first_team_goals = State()
    waiting_for_second_team_goals = State()
    waiting_for_penalty_winner = State()


async def start_bet_process(message: Message, state: FSMContext, pg_con: PostgresConnection, new_bet=True):
    await state.clear()

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
                    and now() - comp.end_date < interval '24 hours'
    where 
            uig.user_id = {message.chat.id}
    """
    comps = await pg_con.get_data(query_get)

    if len(comps) == 0:
        await message.answer("You don't participate in any competition!")
        return

    elif len(comps) > 1:
        keyboard_buttons = []
        for comp in comps:
            keyboard_buttons.append([InlineKeyboardButton(text=comp['c_g_pair'],
                                                          callback_data=f"competition_{comp['competition_id']}_"
                                                                        f"{comp['group_id']}")])
        keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
        msg = await message.answer("Please choose a competition and group pair:", reply_markup=keyboard)
        await state.update_data(previous_message_id=msg.message_id)
        await state.set_state(OrderPlaceBets.waiting_for_comp_and_group_picking)
    else:
        await state.update_data(competition_id=comps[0]['competition_id'], group_id=comps[0]['group_id'])
        await start_picking_match(message, state, pg_con, new_bet=new_bet)


async def start_placing_a_bet(message: Message, state: FSMContext, pg_con: PostgresConnection):
    await start_bet_process(message, state, pg_con, new_bet=True)


async def start_changing_a_bet(message: Message, state: FSMContext, pg_con: PostgresConnection):
    await start_bet_process(message, state, pg_con, new_bet=False)


async def competition_picked(call: CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    competition_id, group_id = call.data.split('_')[1], call.data.split('_')[2]
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(competition_id=competition_id, group_id=group_id)
    await start_picking_match(call.message, state, pg_con)


async def start_picking_match(message: Message, state: FSMContext, pg_con: PostgresConnection, new_bet=True):
    user_data = await state.get_data()
    if new_bet:
        query_get = f"""
        select 
                first_team || ' - ' || second_team as pair
                ,id
                ,{message.chat.id} as user_id
                ,dt::timestamp - interval '3 hours' as dt_in_utc_0
                ,'' as existing_bet
        from 
                bets.matches 
        where
                not exists (select 1 from bets.bets where bets.matches.id = bets.bets.match_id
                and bets.bets.user_id = {message.chat.id})
                and competition_id = {user_data['competition_id']}
                and dt - now() > interval '1 hours'
        order by dt
        """
    else:
        query_get = f"""
        with pre_final as 
        (
        select 
                mtchs.first_team || ' - ' || mtchs.second_team as pair
                ,betting.match_id as id
                ,{message.chat.id} as user_id
                ,mtchs.dt::timestamp - interval '3 hours' as dt_in_utc_0
                ,betting.first_team_goals || ':' || betting.second_team_goals || 
                    case 
                        when betting.penalty_winner = 0 then '' 
                        else ', ' || betting.penalty_winner || ' team wins penalty'
                    end
                as existing_bet
                ,row_number() over (partition by betting.match_id order by betting.insert_date desc) as rn
        from 
                bets.bets as betting
        join 
                bets.matches as mtchs
                    on betting.match_id = mtchs.id
        where
                betting.user_id = {message.chat.id}
                and mtchs.dt - now() > interval '1 hours'
                and betting.competition_id = {user_data['competition_id']}
                and betting.group_id = {user_data['group_id']}
        )
        select 
                pair
                ,id
                ,user_id
                ,dt_in_utc_0
                ,existing_bet
        from
                pre_final
        where 
                rn = 1
        order by dt_in_utc_0
        """

    teams = await pg_con.get_data(query_get)

    if len(teams) == 0:
        await message.answer("You've placed all the bets!")
        return

    keyboard_buttons = []
    text_for_message = "Please choose a match:\n"
    for team in teams:
        callback_data = f"match_{team['id']}_{team['pair']}_{team['user_id']}"
        keyboard_buttons.append([InlineKeyboardButton(text=team['pair'], callback_data=callback_data)])
        existing_part = '' if new_bet else f" ⚽{team['existing_bet']}"
        text_for_message += f"🏟{team['pair']}{existing_part} ⏱️{team['dt_in_utc_0']} UTC+0\n"
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

    msg = await message.answer(text_for_message, reply_markup=keyboard)
    await state.update_data(previous_message_id=msg.message_id)
    await state.set_state(OrderPlaceBets.waiting_for_match_picking)


async def match_picked(call: CallbackQuery, state: FSMContext):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    match_id, pair, user_id = call.data.split('_')[1], call.data.split('_')[2], call.data.split('_')[3]
    await state.update_data(match_id=match_id, pair=pair, user_id=user_id)
    first_team_name = pair.split('-')[0].strip()
    msg = await call.message.answer(f"Please enter the goals for the {first_team_name}:",
                                    reply_markup=generate_number_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await state.set_state(OrderPlaceBets.waiting_for_first_team_goals)


async def first_team_goals_entered(call: CallbackQuery, state: FSMContext):
    first_team_goals = int(call.data.split('_')[1])
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(first_team_goals=first_team_goals)
    second_team_name = user_data['pair'].split('-')[1].strip()
    msg = await call.message.answer(f"Please enter the goals for the {second_team_name}:",
                                    reply_markup=generate_number_keyboard())
    await state.update_data(previous_message_id=msg.message_id)
    await state.set_state(OrderPlaceBets.waiting_for_second_team_goals)


async def second_team_goals_entered(call: CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    second_team_goals = int(call.data.split('_')[1])
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    await state.update_data(second_team_goals=second_team_goals)
    first_team_name, second_team_name = user_data['pair'].split(' - ')

    if user_data['first_team_goals'] == second_team_goals:
        msg = await call.message.answer("The scores are equal. Please choose the penalty winner:",
                                        reply_markup=generate_teams_keyboard(first_team_name, second_team_name))
        await state.update_data(previous_message_id=msg.message_id)
        await state.set_state(OrderPlaceBets.waiting_for_penalty_winner)
    else:
        await state.update_data(penalty_winner=0)
        await save_bet(call, state, pg_con)


async def penalty_winner_entered(call: CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await call.message.bot.delete_message(call.message.chat.id, user_data['previous_message_id'])
    penalty_winner = int(call.data.split('_')[1])
    await state.update_data(penalty_winner=penalty_winner)
    await save_bet(call, state, pg_con)


async def save_bet(call: CallbackQuery, state: FSMContext, pg_con: PostgresConnection):
    user_data = await state.get_data()
    await pg_con.insert_data('bets.bets',
                             ['match_id', 'user_id', 'first_team_goals', 'second_team_goals',
                              'penalty_winner', 'group_id', 'competition_id'],
                             [(user_data['match_id'], user_data['user_id'], user_data['first_team_goals'],
                               user_data['second_team_goals'], user_data['penalty_winner'],
                               user_data['group_id'], user_data['competition_id'])])

    await call.message.answer("Your bet has been placed successfully!", reply_markup=ReplyKeyboardRemove())
    logger.info(f'Bet for match {user_data["match_id"]} for user {user_data["user_id"]} is written successfully')
    await state.clear()


def register_handlers_add_bet(router: Router, pg_con: PostgresConnection):
    async def start_placing_a_bet_wrapper(message: Message, state: FSMContext):
        await start_placing_a_bet(message, state, pg_con)

    async def penalty_winner_entered_wrapper(call: CallbackQuery, state: FSMContext):
        await penalty_winner_entered(call, state, pg_con)

    async def second_team_goals_entered_wrapper(call: CallbackQuery, state: FSMContext):
        await second_team_goals_entered(call, state, pg_con)

    async def competition_picked_wrapper(call: CallbackQuery, state: FSMContext):
        await competition_picked(call, state, pg_con)

    async def start_changing_a_bet_wrapper(message: Message, state: FSMContext):
        await start_changing_a_bet(message, state, pg_con)

    router.message.register(start_placing_a_bet_wrapper, Command("add_bet"), StateFilter("*"))
    router.message.register(start_changing_a_bet_wrapper, Command("change_bet"), StateFilter("*"))
    router.callback_query.register(competition_picked_wrapper, F.data.startswith('competition_'),
                                   StateFilter(OrderPlaceBets.waiting_for_comp_and_group_picking))
    router.callback_query.register(match_picked, F.data.startswith('match_') or F.data.startswith('change_'),
                                   StateFilter(OrderPlaceBets.waiting_for_match_picking))
    router.callback_query.register(first_team_goals_entered, F.data.startswith('goals_'),
                                   StateFilter(OrderPlaceBets.waiting_for_first_team_goals))
    router.callback_query.register(second_team_goals_entered_wrapper, F.data.startswith('goals_'),
                                   StateFilter(OrderPlaceBets.waiting_for_second_team_goals))
    router.callback_query.register(penalty_winner_entered_wrapper, F.data.startswith('penalty_'),
                                   StateFilter(OrderPlaceBets.waiting_for_penalty_winner))
