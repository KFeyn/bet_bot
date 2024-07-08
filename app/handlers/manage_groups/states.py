from aiogram.dispatcher.filters.state import State, StatesGroup


class OrderCreateGroup(StatesGroup):
    waiting_for_comp_picking = State()
    waiting_for_money_picking = State()


class OrderDeleteGroup(StatesGroup):
    waiting_for_group_picking = State()


class OrderDeleteUser(StatesGroup):
    waiting_for_group_picking = State()
    waiting_for_user_picking = State()


class ManageGroupsMenu(StatesGroup):
    waiting_for_action_choice = State()
