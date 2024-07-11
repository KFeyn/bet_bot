# Betting Bot

This bot allows users to place bets on various competitions. It provides functionality to create groups within competitions, set betting amounts, generate invite links for group participation, and manage group memberships. Users can also check the status of their bets, view competition details, and see leaderboards within their groups.

## Features

- **Group Management**: Create, delete groups, and manage group memberships.
- **Betting**: Place bets on matches within competitions.
- **Competition Management**: Check ongoing competitions and their details.
- **Leaderboards**: View leaderboards to see top players within groups.
- **Invite Link Generation**: Generates a unique invite link for each group, facilitating easy addition of members.
- **Betting Amount**: Users can specify the amount of money for their bets within their groups.

## Technical Overview

The bot is built using Python and leverages the `aiogram` framework for asynchronous Telegram bot development. It utilizes `asyncpg` for efficient asynchronous communication with PostgreSQL databases, ensuring fast and reliable data storage and retrieval.

### Key Components

- **State Management**: Utilizes `aiogram`'s state management to handle different stages of group creation, betting, and competition management.
- **Database Interaction**: Uses `asyncpg` for database operations, including checking group limits, inserting new groups, handling betting amounts, and managing competition data.
- **Error Handling**: Implements error handling for unique constraint violations and unexpected database errors, ensuring robustness.
- **Visualization**: Generates visual representations for match outcomes and leaderboards.

## Getting Started

To start using the bot, users need to interact with it on Telegram. The bot guides users through the process of selecting a competition, creating a group, setting a betting amount, and sharing the invite link with potential group members.

### Prerequisites

- Python 3.8+
- `aiogram`
- `asyncpg`
- A PostgreSQL database

## Development

This bot is designed with modularity and scalability in mind, allowing for easy addition of new features and competitions. Contributions and feedback are welcome to enhance its capabilities and user experience.