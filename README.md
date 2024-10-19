# ShowdownLLMPlayer

ShowdownLLMPlayer is an AI-powered Pokémon battle bot designed to play Pokémon Showdown's Random Battles format using advanced language models.

## Features

- Utilizes a large language model for strategic decision-making
- Supports Generation 9 Random Battles format
- Analyzes type effectiveness, move impacts, and team compositions
- Provides detailed reasoning for each move selection

## Requirements

- Python 3.8+
- OptiLLM for efficient language model inference

## Installation

1. Clone the repository:
   ```
   git clone https://github.com/yourusername/ShowdownLLMPlayer.git
   cd ShowdownLLMPlayer
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your environment variables:
   Create a `.env` file in the project root and add your Pokémon Showdown account credentials and Azure OpenAI API key:
   ```
   ACCT_PASSWORD=your_password_here
   INCOMING_USERNAME=your_username_here
   AZURE_OPENAI_API_KEY=your_api_key_here
   ```

## Usage

To start the bot and connect it to Pokémon Showdown:

1. Ensure OptiLLM is running on your local machine (default: http://localhost:8000)

2. Run the main script:
   ```
   python play_showdown.py
   ```

3. The bot will automatically log in and start laddering or accepting challenges based on the configuration in `play_showdown.py`.

## How It Works

ShowdownLLMPlayer uses OptiLLM to efficiently leverage a large language model for analyzing the current battle state, including:

- Team compositions
- Type advantages/disadvantages
- Available moves and their potential impacts
- Battle history

Based on this analysis, the model generates a detailed reasoning process and selects the most strategic move for each turn.

## Customization

You can modify the `ShowdownLLMPlayer` class in `ShowdownLLMPlayer.py` to adjust the bot's behavior or integrate different language models. The `use_local_llm` parameter allows switching between local and Azure-hosted models.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the [Apache License 2.0](LICENSE).