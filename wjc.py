import json
import requests
import csv
import io
import os
from datetime import datetime

URL = "https://stats.sports.bellmedia.ca/sports/hockey/leagues/iihf_juniors/sortablePlayerSeasonStats/"
PARAMS = {
    "brand": "tsn",
    "type": "json",
    "seasonType": "regularSeason",
    "season": "2025",
}


def process_player_submissions():
    teams = []

    submissions = [f for f in os.listdir("submissions") if f.endswith(".csv")]

    for submission in submissions:
        players = {}
        country_goalie = None

        with open(f"./submissions/{submission}", "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                print(row)

                country = row["country"].strip().lower()
                is_goalie = row["is_goalie"].strip().lower() == "true"

                if is_goalie:
                    country_goalie = country
                    continue

                first = row["firstName"].strip().lower()
                last = row["lastName"].strip().lower()

                player_key = clean(first + last)
                if player_key in players:
                    print(f"Duplicate player found: {first} {last}")
                else:
                    players[player_key] = {
                        "first_name": first,
                        "last_name": last,
                        "country": country,
                        "score": None,
                        "found": False,
                    }

        submission_name = submission.split(".")[0]
        teams.append(
            {
                "submission": submission_name,
                "players": players,
                "score": 0,
                "country_goalie": country_goalie,
                "goalie_score": None,
                "goalie_found": False,
            }
        )

    return teams


def compute_scores(teams, url, params):
    print("Computing scores for skaters...")
    skaters = requests.get(url + "skater", params=params)
    skaters = skaters.json()
    teams = get_result_set_scores(skaters, teams)

    print("Computing scores for goalies...")
    goalies = requests.get(url + "goaltender", params=params)
    goalies = goalies.json()

    teams = get_result_set_scores(goalies, teams)
    return teams


def assign_player_scores(player):
    if player["position"] in ("C", "RW", "LW", "F"):
        return (
            int(player.get("goals", 0)) * 1.5 + int(player.get("assists", 0)) * 1.0,
            "F",
        )
    if player["position"] in ("D", "LD", "RD"):
        return (
            int(player.get("goals", 0)) * 3.0 + int(player.get("assists", 0)) * 2.0,
            "D",
        )
    if player["position"] in ("G"):
        return (
            int(player.get("saves", 0)) * 0.15
            + int(player.get("wins", 0)) * 5.0
            + int(player.get("shutouts", 0)) * 5.0
        ) - int(player.get("losses", 0)) * 3, "G"
    return 0


def clean(player_name):
    return player_name.strip().lower()


def get_result_set_scores(players, teams):
    for player in players:
        score, position = assign_player_scores(player["stats"])

        # GOALIES: assign by country
        if position == "G":
            competitor = player["stats"].get("competitor-seo-identifier")
            if not competitor:
                continue

            for team in teams:
                if team["country_goalie"] == competitor.lower():
                    if team["goalie_score"] is None:
                        team["goalie_score"] = 0
                    team["score"] += score
                    team["goalie_score"] += score
                    team["goalie_found"] = True
            continue

        # SKATERS: assign by name
        player_name = clean(player["stats"]["firstName"] + player["stats"]["lastName"])

        for team in teams:
            if player_name in team["players"]:
                if team["players"][player_name]["score"] is None:
                    team["players"][player_name]["score"] = 0
                team["score"] += score
                team["players"][player_name]["score"] += score
                team["players"][player_name]["found"] = True

    return teams


if __name__ == "__main__":
    teams = process_player_submissions()
    teams = compute_scores(teams, URL, PARAMS)
    teams.sort(key=lambda x: x["score"], reverse=True)
    output = {
        "teams": [
            {
                "rank": idx + 1,
                "name": team["submission"],
                "score": round(team["score"], 2),
                "players": sorted(
                    [
                        {
                            "name": f"{p['first_name'].title()} {p['last_name'].title()}",
                            "score": round(p["score"], 2) if p["found"] else None,
                        }
                        for p in team["players"].values()
                    ]
                    + (
                        [
                            {
                                "name": f"Goalie ({team['country_goalie'].title()})",
                                "score": (
                                    round(team["goalie_score"], 2)
                                    if team["goalie_found"]
                                    else None
                                ),
                            }
                        ]
                        if team["country_goalie"]
                        else []
                    ),
                    key=lambda x: (
                        x["score"] is not None and x["score"] > 0,
                        x["score"] is not None and x["score"] == 0,
                        x["score"] if x["score"] is not None else -1,
                    ),
                    reverse=True,
                ),
            }
            for idx, team in enumerate(teams)
        ]
    }

    # Write to scores folder with timestamp
    os.makedirs("./scores", exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    filename = f"./scores/scores-{timestamp}.json"
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    # Write latest.json pointing to most recent file
    latest = {"file": f"scores/scores-{timestamp}.json", "timestamp": timestamp}
    with open("./latest.json", "w", encoding="utf-8") as f:
        json.dump(latest, f, indent=2)
