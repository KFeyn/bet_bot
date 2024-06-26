from __future__ import annotations
import dataclasses
from app.dbworker import PostgresConnection
import logging


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
            logging.info(f'User {self.nickname} created')
