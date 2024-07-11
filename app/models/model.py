from __future__ import annotations
import dataclasses
from app.dbworker.dbworker import PostgresConnection
from app.utils.utilities import logger, generate_id
import datetime


@dataclasses.dataclass
class User:
    id: int
    first_name: str
    last_name: str
    nickname: str

    @classmethod
    def from_id(cls, row: tuple) -> User:
        return cls(
            id=int(row[0]),
            first_name=str(row[1]),
            last_name=str(row[2]),
            nickname=str(row[3])
        )

    async def check_existing(self, pg_con: PostgresConnection) -> None:
        query = f"""
        select 
                id
        from 
                bets.users
        where 
                id = '{self.id}'
        """
        if await pg_con.get_data(query):
            pass
        else:
            await pg_con.insert_data('bets.users', ['id', 'first_name', 'last_name', 'nickname'],
                                     [(self.id, self.first_name, self.last_name, self.nickname)])
            logger.info(f'User {self.nickname} created')


@dataclasses.dataclass
class Competition:
    name: str
    year: int
    need_to_parse: bool
    api_url: str
    competition_code: str
    id: int

    @classmethod
    def from_message(cls, row: tuple) -> Competition:
        nm = str(row[0])
        full_nm = str(nm) + ' ' + str(datetime.date.today().year)
        nm_for_api = nm if nm != 'Euro' else 'EC'
        return cls(
            name=full_nm,
            year=datetime.date.today().year,
            need_to_parse=True,
            api_url=f'https://api.football-data.org/v4/competitions/{nm_for_api}/matches',
            competition_code=nm_for_api,
            id=generate_id(full_nm)
        )

    async def check_existing(self, pg_con: PostgresConnection) -> None:
        query = f"""
        select 
                name
        from 
                bets.competitions
        where 
                id = {self.id} 
        """
        if await pg_con.get_data(query):
            pass
        else:
            await pg_con.insert_data('bets.competitions',
                                     ['name', 'year', 'need_to_parse', 'api_url', 'competition_code'],
                                     [(self.name, self.year, self.need_to_parse, self.api_url, self.competition_code)])
            logger.info(f'Competition {self.name} created')


@dataclasses.dataclass
class UserInGroup:
    user_id: int
    group_id: int
    added_by: int
    is_admin: bool

    @classmethod
    def from_message(cls, row: tuple) -> UserInGroup:
        return cls(
            user_id=int(row[0]),
            group_id=int(row[1]),
            added_by=int(row[2]),
            is_admin=False
        )

    async def check_existing_group(self, pg_con: PostgresConnection) -> bool:
        query = f"""
        select 
                id
        from 
                bets.groups
        where 
                id = {self.group_id}
        """
        if await pg_con.get_data(query):
            return True
        return False

    async def check_existing(self, pg_con: PostgresConnection) -> None:
        query = f"""
        select 
                id
        from 
                bets.users_in_groups
        where 
                user_id = {self.user_id}
                and group_id = {self.group_id}
        """
        if await pg_con.get_data(query):
            pass
        else:
            await pg_con.insert_data('bets.users_in_groups',
                                     ['user_id', 'group_id', 'added_by', 'is_admin'],
                                     [(self.user_id, self.group_id, self.added_by, self.is_admin)])
            logger.info(f'User {self.user_id} added to group {self.group_id}')
