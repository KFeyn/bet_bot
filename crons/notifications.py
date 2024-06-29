import os
import psycopg2
import requests
import logging
import typing as tp

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
for handler in logger.handlers:
    handler.setFormatter(formatter)


def make_dict(records: tp.List) -> tp.Dict:
    users_matches = dict()
    for record in records:
        first_name, user_id, pair, group_name, competition_name, dt = record
        if user_id not in users_matches:
            users_matches[str(user_id)] = [[first_name, pair, group_name, competition_name, dt]]
        else:
            users_matches[str(user_id)].append([first_name, pair, group_name, competition_name, dt])
    return users_matches


def make_message(attributes: tp.List) -> str:
    msg = f'Hi {attributes[0][0]}, you didn\'t placed a bet for:\n\n'
    for el in attributes:
        msg += f'<b>{el[1]}</b> at competition <b>{el[3]}</b> at {el[4]} UTC+0\n\n'
    msg += 'Please, place a bet using /add_bet'
    return msg


def send_to_channel(message: str, chat_id: str, user_name: str) -> None:
    bot_token = os.environ.get('BOT_TOKEN')

    params = {
        'chat_id': chat_id,
        'text': message,
        'parse_mode': 'HTML',
    }
    url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
    print(params)
    response = requests.post(url, data=params)

    if response.status_code == 200:
        logger.info(f'Message for {user_name} sent successfully')
    else:
        logger.error(f'Failed to send message for {user_name}: {response.status_code} - {response.text}')


def get_data_from_db(query: str) -> tp.List:
    try:

        connection = psycopg2.connect(
            dbname=os.environ.get('PG_db'),
            user=os.environ.get('PG_user'),
            password=os.environ.get('PG_password'),
            host=os.environ.get('PG_host'),
            port=6432
        )

        cursor = connection.cursor()
        cursor.execute(query)
        records = cursor.fetchall()

        cursor.close()
        connection.close()

        return records

    except Exception as e:
        logger.error(f"Error fetching data from database: {e}")
        return []


def main():
    query = """
        select 
            usr.first_name 
            ,usr.id as user_id
            ,mtch.first_team || ' - ' || mtch.second_team as pair
            ,grps.name as group_name
            ,cmpt.name as competition_name
            ,mtch.dt - interval '3 hours' as dt
        from 
            bets.users as usr
        join 
            bets.users_in_groups as uig
                on uig.user_id = usr.id
        join
            bets.groups as grps
                on grps.id = uig.group_id
        join
            bets.groups_in_competitions as gic
                on gic.group_id = grps.id
        join 
            bets.competitions as cmpt
                on cmpt.id = gic.competition_id
        join 
            bets.matches as mtch
                on mtch.competition_id = cmpt.id
        where 
            not exists (select 1 from bets.bets as bts where bts.user_id = usr.id and bts.competition_id = cmpt.id and 
            bts.group_id = grps.id and bts.match_id = mtch.id)
            and dt - now() < interval '12 hours'
        order by usr.first_name, mtch.dt
    """
    records = get_data_from_db(query)

    users_matches = make_dict(records)

    for user in users_matches:
        message = make_message(users_matches[user])
        send_to_channel(message, user, users_matches[user][0][0])


if __name__ == '__main__':
    main()
