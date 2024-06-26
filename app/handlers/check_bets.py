import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup

from ..dbworker import PostgresConnection


class OrderCheckBets(StatesGroup):
    waiting_for_match_picking = State()
    waiting_for_first_team_goals = State()
    waiting_for_second_team_goals = State()
    waiting_for_penalty_winner = State()