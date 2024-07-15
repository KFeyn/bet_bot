import requests
import psycopg2
import psycopg2.extras
import hashlib
from datetime import datetime, timedelta
import logging
import typing as tp
import os

logger = logging.getLogger()
logger.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(name)s - %(message)s')
for handler in logger.handlers:
    handler.setFormatter(formatter)


def create_dt(dt: str) -> str:
    original_date = datetime.fromisoformat(dt.replace("Z", "+00:00"))
    original_date = original_date + timedelta(hours=3)
    return original_date.strftime("%Y-%m-%d %H:%M:%S%z").replace('0000', '03')


def generate_id(value: str) -> int:
    md5_hash = hashlib.md5(value.encode()).hexdigest()
    first_16_chars = md5_hash[:16]
    integer_value = int(first_16_chars, 16)
    if integer_value >= 2 ** 63:
        integer_value -= 2 ** 64
    return integer_value


class Competition:
    def __init__(self, start_date: str, last_date: str, code: str, season: str):
        self.start_date = create_dt(start_date)
        self.last_date = create_dt(last_date)
        self.code = code
        self.name = f"{code} {season}" if code != 'EC' else f"Euro {season}"
        self.season = season
        self.id = generate_id(self.name)
        self.api_url = f'https://api.football-data.org/v4/competitions/{self.code}/matches'
        self.date_to_compare = datetime.strptime(last_date, '%Y-%m-%d')


class Match:
    def __init__(self, match_data: tp.Dict, competition: Competition):
        self.first_team = match_data['homeTeam']['name']
        self.second_team = match_data['awayTeam']['name']
        self.competition_id = competition.id
        self.first_team_goals = match_data['score']['fullTime']['home']
        self.second_team_goals = match_data['score']['fullTime']['away']
        self.status = match_data['status']

        penalties = match_data['score'].get('penalties')
        if penalties:
            self.first_team_goals = self.first_team_goals - penalties['home']
            self.second_team_goals = self.second_team_goals - penalties['away']
            if penalties['home'] > penalties['away']:
                self.penalty_winner = 1
            else:
                self.penalty_winner = 2
        elif self.first_team_goals is None:
            self.penalty_winner = None
        else:
            self.penalty_winner = 0
        self.dt = create_dt(match_data['utcDate'])

        stage_type = f"{match_data['stage']}_{match_data['matchday']}" if match_data['stage'] == 'GROUP_STAGE' else (
            match_data)['stage']
        stage_map = {
            'GROUP_STAGE_1': 'group matchday 1',
            'GROUP_STAGE_2': 'group matchday 2',
            'GROUP_STAGE_3': 'group matchday 3',
            'GROUP_STAGE_4': 'group matchday 4',
            'GROUP_STAGE_5': 'group matchday 5',
            'GROUP_STAGE_6': 'group matchday 6',
            'LAST_32': '1/16 final',
            'LAST_16': '1/8 final',
            'QUARTER_FINALS': '1/4 final',
            'SEMI_FINALS': '1/2 final',
            'THIRD_PLACE': 'final',
            'FINAL': 'final'
        }
        self.stage = stage_map.get(stage_type)


def process_data(data) -> tp.List[Match]:
    competition_code = data['competition']['code']
    season = data['filters']['season']

    last_day_str = data['resultSet']['last']
    first_day_str = data['resultSet']['first']

    competition = Competition(first_day_str, last_day_str, competition_code, season)

    if datetime.now() > competition.date_to_compare + timedelta(days=1):
        logger.info("Competition last day is more than one day ahead, no need to process")
        return []

    matches = []
    for match_data in data['matches']:
        match = Match(match_data, competition)
        if match.first_team and match.second_team:
            matches.append(match)

    logger.info(f"Processed {len(matches)} matches")
    return matches


def fetch_and_process_data(api_url: str, api_key: str) -> tp.List[Match]:
    logger.info(f"Fetching data from API: {api_url}")
    response = requests.get(api_url, headers={'X-Auth-Token': api_key})
    if response.status_code == 200:
        logger.info("Data fetched successfully from API")
        data = response.json()
        return process_data(data)
    else:
        logger.error("Failed to fetch data from API")
        raise Exception("Failed to fetch data from API")


def fetch_competitions_to_choose(api_key: str) -> tp.List[Competition]:
    comps = []
    api_url = f'https://api.football-data.org/v4/competitions'
    response = requests.get(api_url, headers={'X-Auth-Token': api_key})
    if response.status_code == 200:
        logger.info("Data fetched successfully from API")
        data = response.json()
    else:
        logger.error("Failed to fetch data from API")
        raise Exception("Failed to fetch data from API")

    for competition in data['competitions']:
        started = competition['currentSeason']['startDate']
        if competition['code'] in ['WC', 'CL', 'EC']:
            logger.info(f"Parsed competition {competition['code']}")
            comps.append(Competition(started, competition['currentSeason']['endDate'], competition['code'],
                                     started[:4]))
    return comps


class DatabaseHandler:
    def __init__(self, dbname: str, user: str, password: str, host: str):
        self.dbname = dbname
        self.user = user
        self.password = password
        self.host = host
        self.connection = None

    def connect(self):
        try:
            self.connection = psycopg2.connect(f'postgresql://{self.user}:{self.password}@{self.host}:'
                                               f'6432/{self.dbname}')
            logger.info("Database connection established")
        except Exception as e:
            logger.error(f"Error connecting to database: {e}")

    def close_connection(self):
        if self.connection:
            self.connection.close()
            self.connection = None
            logger.info("Database connection closed")

    def check_existing_competition(self, competitions: tp.List[Competition]):
        ids_list = ', '.join([str(competition.id) for competition in competitions])
        try:
            self.connect()
            cursor = self.connection.cursor()
            query = f"""
                    select 
                            id
                    from 
                            bets.competitions
                    where 
                            id in ({ids_list})
            """
            cursor.execute(query)
            competition_db = cursor.fetchall()
            cursor.close()
        except Exception as e:
            logger.error(f"Error fetching competitions: {e}")
            return
        finally:
            self.close_connection()
        existing_competitions = [comp[0] for comp in competition_db]
        new_competitions = [competition for competition in competitions if competition.id not in existing_competitions]
        if not new_competitions:
            return
        else:
            logger.info(f"Inserting {len(new_competitions)} competitions into the database")
            insert_query = """
                    INSERT INTO bets.competitions 
                    (name, year, need_to_parse, api_url, competition_code, start_date, end_date)
                    VALUES %s
                """
            insert_data = [(competition.name, competition.season, True, competition.api_url, competition.code,
                           competition.start_date, competition.last_date) for competition in new_competitions]
            try:
                self.connect()
                cursor = self.connection.cursor()
                psycopg2.extras.execute_values(cursor, insert_query, insert_data)
                self.connection.commit()
            except Exception as e:
                logger.error(f"Error inserting or updating matches: {e}")
                self.connection.rollback()
            finally:
                self.close_connection()

    def fetch_competitions_to_parse(self) -> tp.List[tp.Tuple[str, str]]:
        try:
            self.connect()
            cursor = self.connection.cursor()
            query = """
                SELECT api_url, competition_code
                FROM bets.competitions
                WHERE need_to_parse = true
            """
            cursor.execute(query)
            competitions = cursor.fetchall()
            cursor.close()
            return competitions
        except Exception as e:
            logger.error(f"Error fetching competitions: {e}")
            return []
        finally:
            self.close_connection()

    def insert_or_update_matches(self, matches: tp.List[Match]):
        if not matches:
            logger.info("No matches to insert or update")
            return

        try:
            self.connect()
            cursor = self.connection.cursor()

            match_ids = [generate_id(f"{match.first_team}{match.second_team}{match.competition_id}{match.dt}") for match
                         in matches]
            match_ids_str = ', '.join(map(str, match_ids))
            logger.info("Fetching existing matches from database")
            cursor.execute(
                f"SELECT id, first_team_goals, second_team_goals, penalty_winner FROM bets.matches WHERE id IN "
                f"({match_ids_str})")
            existing_matches = cursor.fetchall()
            existing_match_data = {row[0]: row for row in existing_matches}

            insert_data = []
            update_data = []

            for match in matches:
                match_id = generate_id(f"{match.first_team}{match.second_team}{match.competition_id}{match.dt}")

                if match_id not in existing_match_data:
                    insert_data.append((match.first_team, match.second_team, match.competition_id, match.dt,
                                        match.first_team_goals, match.second_team_goals, match.penalty_winner,
                                        match.stage))
                elif existing_match_data[match_id][1] is None and match.status == 'FINISHED':
                    update_data.append((match.first_team_goals, match.second_team_goals, match.penalty_winner,
                                        match_id))

            if insert_data:
                logger.info(f"Inserting {len(insert_data)} new matches into the database")
                insert_query = """
                    INSERT INTO bets.matches 
                    (first_team, second_team, competition_id, dt, first_team_goals, second_team_goals, penalty_winner, 
                    stage)
                    VALUES %s
                """
                psycopg2.extras.execute_values(cursor, insert_query, insert_data)

            if update_data:
                logger.info(f"Updating {len(update_data)} existing matches in the database")
                update_query = """
                    UPDATE bets.matches
                    SET first_team_goals = %s, second_team_goals = %s, penalty_winner = %s
                    WHERE id = %s
                """
                cursor.executemany(update_query, update_data)

            self.connection.commit()
            cursor.close()
            logger.info("Database operations completed successfully")
        except Exception as e:
            logger.error(f"Error inserting or updating matches: {e}")
            self.connection.rollback()
        finally:
            self.close_connection()

    def update_competition(self):

        try:
            self.connect()
            cursor = self.connection.cursor()
            parse_query = """
                update bets.competitions
                set 
                    need_to_parse = False
                where 
                    need_to_parse = True
                    and now() - end_date > interval '2 days'
            """
            cursor.execute(parse_query)
            self.connection.commit()
            cursor.close()

        except Exception as e:
            logger.error(f"Error fetching competitions: {e}")
            return
        finally:
            self.close_connection()


def main():
    db_handler = DatabaseHandler(dbname=os.environ.get('PG_db'),
                                 user=os.environ.get('PG_user'),
                                 password=os.environ.get('PG_password'),
                                 host=os.environ.get('PG_host')
                                 )
    api_key = os.environ.get('API_KEY')

    competitions_to_add = fetch_competitions_to_choose(api_key)
    db_handler.check_existing_competition(competitions_to_add)
    db_handler.update_competition()

    competitions = db_handler.fetch_competitions_to_parse()
    for api_url, competition_code in competitions:
        matches = fetch_and_process_data(api_url, api_key)
        db_handler.insert_or_update_matches(matches)


if __name__ == '__main__':
    main()
