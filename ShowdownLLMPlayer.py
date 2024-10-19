import orjson
from poke_env.environment.battle import Battle
from poke_env.player.battle_order import BattleOrder
from poke_env import AccountConfiguration, ShowdownServerConfiguration
from poke_env.player.player import Player

import json
import os
from typing import Dict, List, Tuple, Optional
import pandas as pd
import random
import requests

from javascript import require
from openai import OpenAI


class ShowdownLLMPlayer(Player):
    def __init__(
        self,
        account_configuration: AccountConfiguration,
        server_configuration: ShowdownServerConfiguration, # type: ignore
        random_strategy: bool = False,
        use_local_llm: bool = False,
    ):
        super().__init__(
            account_configuration=account_configuration,
            server_configuration=server_configuration,
            save_replays=True,
            battle_format="gen9randombattle",
            start_timer_on_battle_start=True,
        )
        self.random_strategy = random_strategy
        self.random_sets: Dict = self._load_random_sets()
        self.move_effects: pd.DataFrame = pd.read_csv("data/moves.csv")
        self.item_lookup: Dict = json.load(open("data/items.json"))
        self.game_history: List[str] = []
        self.fainted: bool = False
        self.api_key: str = os.getenv("AZURE_OPENAI_API_KEY", "")
        self.use_local_llm: bool = use_local_llm

    def _load_random_sets(self) -> Dict:
        random_sets = requests.get(
            "https://pkmn.github.io/randbats/data/gen9randombattle.json"
        ).json()
        return {k.lower(): v for k, v in random_sets.items()}

    def _contact_llm(self, message: str) -> str:
        system_prompt = "You are an expert Pokemon battle strategist called showdown-dojo. Analyze the given situation and provide a detailed response."
        OPTI_LLM_BASE_URL = "http://localhost:8000/v1"
        client = OpenAI(api_key=self.api_key, base_url=OPTI_LLM_BASE_URL)
        response = client.chat.completions.create(
            model="ollama/llama3.2" if self.use_local_llm else "gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ],
            temperature=0.2,
            extra_body={"optillm_approach": "mcts"},
        )
        response_content = response.choices[0].message.content
        print("RESPONSE: ", response_content)
        return response_content

    def _generate_prompt(
        self,
        game_history: str,
        player_team: str,
        opponent_team: str,
        player_moves_impact: str,
        opponent_moves_impact: str,
        player_active: str,
        opponent_active: str,
        available_choices: str,
        fainted: bool,
    ) -> str:
        type_effectiveness_prompt = """
Type effectiveness summary:
Normal: Weak to Fighting
Fire: Strong vs Grass/Ice/Bug/Steel, Weak to Water/Ground/Rock
Water: Strong vs Fire/Ground/Rock, Weak to Electric/Grass
Electric: Strong vs Water/Flying, Weak to Ground
Grass: Strong vs Water/Ground/Rock, Weak to Fire/Ice/Poison/Flying/Bug
Ice: Strong vs Grass/Ground/Flying/Dragon, Weak to Fire/Fighting/Rock/Steel
Fighting: Strong vs Normal/Ice/Rock/Dark/Steel, Weak to Flying/Psychic/Fairy
Poison: Strong vs Grass/Fairy, Weak to Ground/Psychic
Ground: Strong vs Fire/Electric/Poison/Rock/Steel, Weak to Water/Grass/Ice
Flying: Strong vs Grass/Fighting/Bug, Weak to Electric/Ice/Rock
Psychic: Strong vs Fighting/Poison, Weak to Bug/Ghost/Dark
Bug: Strong vs Grass/Psychic/Dark, Weak to Fire/Flying/Rock
Rock: Strong vs Fire/Ice/Flying/Bug, Weak to Water/Grass/Fighting/Ground/Steel
Ghost: Strong vs Psychic/Ghost, Weak to Ghost/Dark
Dragon: Strong vs Dragon, Weak to Ice/Dragon/Fairy
Dark: Strong vs Psychic/Ghost, Weak to Fighting/Bug/Fairy
Steel: Strong vs Ice/Rock/Fairy, Weak to Fire/Fighting/Ground
Fairy: Strong vs Fighting/Dragon/Dark, Weak to Poison/Steel
"""
        prompt_template = """You are an expert Pokemon battle strategist. Analyze the given situation and provide a detailed response.

Scenario: [SCENARIO]

1. Briefly overview the current battle situation, including active Pokémon, their health, and any field conditions.
2. Analyze the type matchups between your active Pokémon and the opponent's.
3. Consider your Pokémon's moves, their effectiveness, and potential secondary effects.
4. Evaluate the opponent's Pokémon, predicting their likely moves and strategy.
5. Assess the risk of the opponent setting up (e.g., boosting stats, applying status conditions, or setting hazards).
6. Examine both Pokémon's abilities and how they might influence your decision.
7. Consider the broader battle context, including remaining team members and their roles.
8. Weigh the pros and cons of switching out versus staying in.
9. Think about potential mind games or predictions based on typical player behavior.
10. Evaluate how your choice might set up future turns or team synergy.
11. Break down your reasoning step-by-step, considering immediate impact and long-term strategy.
12. Conclude with a clear recommendation, explaining why it's likely the optimal choice given the current situation.

Type effectiveness: [TYPE EFFECTIVENESS CHART]

Your team: [PLAYER_TEAM_INFO]
Opponent's team: [OPPONENT_TEAM_INFO]

Be mindful to not confusing your own pokemon with the opponent's.

Your [PLAYER_POKEMON]'s move impacts:
[PLAYER_MOVES_IMPACT]

Opponent's [OPPONENT_POKEMON]'s move impacts:
[OPPONENT_MOVES_IMPACT]

Your choices:
[CHOICES]

Format your response as:
<Summary>
<Analysis>
<Conclusion>
<Choice>

End with: "Final choice: [choice number]"
"""

        prompt_template_fainted = prompt_template.replace(
            "Your [PLAYER_POKEMON]'s move impacts:\n[PLAYER_MOVES_IMPACT]\n\nOpponent's [OPPONENT_POKEMON]'s move impacts:\n[OPPONENT_MOVES_IMPACT]\n",
            "Your [PLAYER_POKEMON] has fainted.\n",
        )

        template = prompt_template_fainted if fainted else prompt_template

        return (
            template.replace("[SCENARIO]", game_history)
            .replace("[TYPE EFFECTIVENESS CHART]", type_effectiveness_prompt)
            .replace("[PLAYER_TEAM_INFO]", player_team)
            .replace("[OPPONENT_TEAM_INFO]", opponent_team)
            .replace("[PLAYER_MOVES_IMPACT]", player_moves_impact)
            .replace("[OPPONENT_MOVES_IMPACT]", opponent_moves_impact)
            .replace("[PLAYER_POKEMON]", player_active)
            .replace("[OPPONENT_POKEMON]", opponent_active)
            .replace("[CHOICES]", available_choices)
        )

    async def _handle_battle_message(self, split_messages: List[List[str]]):
        battle_log = []
        for event in split_messages:
            if len(event) > 1 and event[1] == "request" and event[2]:
                request = orjson.loads(event[2])
                pokemons = request["side"]["pokemon"]
                for pokemon in pokemons:
                    if pokemon["active"] and pokemon["condition"] == "0 fnt":
                        self.fainted = True
            message = "|".join(event)
            if not any(message.startswith(prefix) for prefix in ("|request", ">", "|upkeep", "|t:")):
                battle_log.append(message)

        if battle_log:
            self.game_history.append("\n".join(battle_log))

        with open("battle_log.txt", "a") as f:
            f.write("\n".join(battle_log))

        await super()._handle_battle_message(split_messages)

    def _find_move_effect(self, move_name: str, move_effects: pd.DataFrame) -> Optional[str]:
        move_effect = move_effects.loc[move_effects["name"] == move_name]
        return list(move_effect.to_dict()["effect"].values())[0] if not move_effect.empty else None

    def _find_potential_random_set(self, team_data: Dict) -> Dict:
        for pokemon in team_data.values():
            pokemon_name = pokemon["name"].strip().lower()
            if pokemon_name in self.random_sets:
                known_moves = set(pokemon["moves"].keys()) if isinstance(pokemon["moves"], dict) else set(pokemon["moves"])
                possible_sets = self.random_sets[pokemon_name]["roles"]
                for role, role_data in possible_sets.items():
                    if known_moves.issubset(role_data["moves"]):
                        pokemon.update({
                            "evs": role_data.get("evs", {}),
                            "ivs": role_data.get("ivs", {}),
                            "moves": {move: "seen" if move in known_moves else "unseen" for move in role_data["moves"]}
                        })
                        break
        return team_data

    def _get_team_data(self, battle: Battle, opponent: bool = False) -> Dict:
        team = battle.opponent_team if opponent else battle.team
        result = {}
        for pokemon in team.values():
            result[pokemon.species] = {
                "moves": {
                    move.entry["name"]: {
                        "type": move.entry["type"],
                        "accuracy": move.entry["accuracy"],
                        "secondary effect": move.entry.get("secondary", None),
                        "base power": move.entry["basePower"],
                        "category": move.entry["category"],
                        "priority": move.entry["priority"],
                        "effect": self._find_move_effect(move.entry["name"], self.move_effects),
                    }
                    for move in pokemon.moves.values()
                },
                "hp": pokemon.current_hp,
                "ability": pokemon.ability,
                "fainted": pokemon.fainted,
                "item": self.item_lookup.get(pokemon.item, ""),
                "tera": pokemon.tera_type.name.lower().capitalize() if pokemon.terastallized else "",
                "name": pokemon._data.pokedex[pokemon.species]["name"],
                "boosts": pokemon.boosts,
                "level": pokemon.level,
            }
        return result

    def _calculate_damage(
        self,
        atkr: Dict,
        defdr: Dict,
        move_used: str,
        opponent: bool = False,
        log: bool = False,
    ) -> Tuple[str, str]:
        damage_calc = require("@smogon/calc")
        generation = damage_calc.Generations.get(9)

        atkr_attributes = {k: v for k, v in atkr.items() if k in ["level", "item", "boosts", "tera", "evs", "ivs"]}
        defdr_attributes = {k: v for k, v in defdr.items() if k in ["level", "item", "boosts", "tera", "evs", "ivs"]}

        try:
            attacker = damage_calc.Pokemon.new(generation, atkr["name"], atkr_attributes)
            defender = damage_calc.Pokemon.new(generation, defdr["name"], defdr_attributes)
        except:
            attacker = damage_calc.Pokemon.new(generation, atkr["name"].split("-")[0], atkr_attributes)
            defender = damage_calc.Pokemon.new(generation, defdr["name"].split("-")[0], defdr_attributes)

        move = damage_calc.Move.new(generation, move_used)
        result = damage_calc.calculate(generation, attacker, defender, move)

        if log:
            print(f"Attacker: {attacker}")
            print(f"Defender: {defender}")
            print(f"Defender HP: {defender.originalCurHP}")
            print(f"Move: {move}")
            print(f"RESULT: {result}")

        if result.damage == 0:
            return "0%", "0%"
        if isinstance(result.damage, str):
            return result.damage, result.damage

        try:
            dmg_range = result.damage.valueOf() if not isinstance(result.damage, int) else [result.damage]
            min_dmg, max_dmg = min(dmg_range), max(dmg_range)
        except Exception as e:
            print(f"ERROR: {e}")
            print(f"INPUTS: {atkr['name']}, {defdr['name']}, {move_used}")
            print(f"RESULT: {result.damage}")
            return "0%", "0%"

        hp = defdr.get("hp") or defdr.get("maximum hp")
        if hp == 0:
            return "100%", "100%"

        if opponent:
            min_dmg_percent = int(min_dmg / (defender.originalCurHP * (hp / 100.0)) * 100)
            max_dmg_percent = int(max_dmg / (defender.originalCurHP * (hp / 100.0)) * 100)
        else:
            min_dmg_percent = int(min_dmg / hp * 100)
            max_dmg_percent = int(max_dmg / hp * 100)

        return f"{min_dmg_percent}%", f"{max_dmg_percent}%"

    def _format_move_impact(self, move_name: str, impact_ranges: Tuple[str, str], pkm_name: str) -> str:
        return f"The move {move_name} will deal between {impact_ranges[0]} and {impact_ranges[1]} damage to {pkm_name}"

    def _format_team_info(self, team_dict: Dict, opponent: bool = False) -> str:
        formatted_team = ""
        for _, details in team_dict.items():
            formatted_team += f"{details['name']}:\n"
            formatted_team += f"  Ability: {details.get('ability', 'Unknown')}\n"
            formatted_team += f"  Item: {details.get('item', 'Unknown')}\n"
            formatted_team += f"  Moves:\n"
            formatted_team += f"  HP: {details['hp']}{'%' if opponent else ''}\n"

            if opponent:
                formatted_team += "\n".join(
                    f"    - {move} ({status})"
                    for move, status in details["moves"].items()
                )
            else:
                formatted_team += "\n".join(
                    f"    - {move} (Type: {md['type']}, Power: {md['base power']}, Accuracy: {md['accuracy']})"
                    for move, md in details["moves"].items()
                )

            if "tera" in details:
                formatted_team += f"  Tera Type: {details['tera']}\n"
            if "boosts" in details:
                formatted_team += f"  Stat Changes: {details['boosts']}\n"
            formatted_team += f"  Status: {'Fainted' if details['fainted'] else 'Active'}\n\n"
        return formatted_team

    def choose_move(self, battle: Battle) -> BattleOrder:
        print("Choosing move")
        player_team = self._get_team_data(battle)
        opponent_team = self._find_potential_random_set(self._get_team_data(battle, opponent=True))

        cur_player_side = player_team[battle.active_pokemon.species]
        cur_opponent_side = opponent_team[battle.opponent_active_pokemon.species]

        player_moves_impact = [
            (move, self._calculate_damage(cur_player_side, cur_opponent_side, move, opponent=True))
            for move in cur_player_side["moves"].keys()
        ]
        player_moves_impact_prompt = "\n".join(
            self._format_move_impact(move, impact, cur_opponent_side["name"])
            for move, impact in player_moves_impact
        )

        opponent_moves_impact = [
            (move, self._calculate_damage(cur_opponent_side, cur_player_side, move))
            for move in cur_opponent_side["moves"].keys()
        ]
        opponent_moves_impact_prompt = "\n".join(
            self._format_move_impact(move, impact, cur_player_side["name"])
            for move, impact in opponent_moves_impact
        )

        available_orders: List[BattleOrder] = [
            BattleOrder(move) for move in battle.available_moves
        ]
        available_orders.extend([BattleOrder(switch) for switch in battle.available_switches])

        if battle.can_mega_evolve:
            available_orders.extend([BattleOrder(move, mega=True) for move in battle.available_moves])
        if battle.can_dynamax:
            available_orders.extend([BattleOrder(move, dynamax=True) for move in battle.available_moves])
        if battle.can_tera:
            available_orders.extend([BattleOrder(move, terastallize=True) for move in battle.available_moves])
        if battle.can_z_move and battle.active_pokemon:
            available_z_moves = set(battle.active_pokemon.available_z_moves)
            available_orders.extend([
                BattleOrder(move, z_move=True)
                for move in battle.available_moves
                if move in available_z_moves
            ])

        available_orders_prompt = "\n".join(
            f"{i + 1}. {str(order).replace('/choose', '').strip()}"
            for i, order in enumerate(available_orders)
        )

        game_history = "\n".join(self.game_history)
        pokemon_fainted = self.fainted
        self.fainted = False

        prompt = self._generate_prompt(
            game_history,
            str(player_team),
            str(opponent_team),
            player_moves_impact_prompt,
            opponent_moves_impact_prompt,
            cur_player_side["name"],
            cur_opponent_side["name"],
            available_orders_prompt,
            pokemon_fainted,
        )

        if not self.random_strategy:
            llm_response = self._contact_llm(prompt)
            try:
                choice = int("".join(filter(str.isdigit, llm_response.lower().split("choice")[1]))) - 1
                return available_orders[choice]
            except:
                if llm_response.strip().isdigit():
                    choice = int(llm_response) - 1
                    print(f"Single digit choice returned: {choice}")
                    return available_orders[choice]
                print("Unable to parse choice, choosing randomly")
        else:
            print("Choosing randomly because random_strategy is True")

        print("Made choice\n")
        return random.choice(available_orders)
