"""
Auto-generate player ratings based on caps, club level, and known star ratings.
Output: data/wc_player_ratings.json

Rating methodology:
- Base from caps (experience): min(caps/150 * 30, 30) + 50
- Club tier bonus: top 5 league +10, other top league +5, rest 0
- Known star players get manual override ratings
"""
import sys, json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# Known star players with manual ratings (FIFA-style 0-99 scale)
STAR_RATINGS = {
    # Argentina
    'Lionel Messi': 88, 'Julián Álvarez': 85, 'Lautaro Martínez': 86,
    'Enzo Fernández': 84, 'Alexis Mac Allister': 84, 'Rodrigo De Paul': 83,
    'Cristian Romero': 85, 'Nicolás Otamendi': 80, 'Emiliano Martínez': 86,
    # Brazil
    'Vinícius Júnior': 90, 'Neymar': 86, 'Rodrygo': 86,
    'Raphinha': 84, 'Casemiro': 82, 'Bruno Guimarães': 85,
    'Marquinhos': 84, 'Éder Militão': 85, 'Alisson': 88,
    # France
    'Kylian Mbappé': 91, 'Antoine Griezmann': 85, 'Ousmane Dembélé': 84,
    'Aurélien Tchouaméni': 86, 'Eduardo Camavinga': 83,
    'William Saliba': 85, 'Dayot Upamecano': 83, 'Mike Maignan': 86,
    # England
    'Harry Kane': 89, 'Jude Bellingham': 88, 'Bukayo Saka': 87,
    'Phil Foden': 86, 'Declan Rice': 86, 'Cole Palmer': 85,
    'John Stones': 83, 'Kyle Walker': 81, 'Jordan Pickford': 83,
    # Germany
    'Jamal Musiala': 87, 'Florian Wirtz': 86, 'İlkay Gündoğan': 84,
    'Joshua Kimmich': 85, 'Jamie Leweling': 80, 'Kai Havertz': 83,
    'Antonio Rüdiger': 84, 'Jonathan Tah': 83, 'Marc-André ter Stegen': 85,
    # Spain
    'Lamine Yamal': 86, 'Pedri': 85, 'Gavi': 84,
    'Rodri': 89, 'Fabián Ruiz': 83, 'Dani Olmo': 83,
    'Aymeric Laporte': 82, 'Dani Carvajal': 83, 'Unai Simón': 83,
    # Portugal
    'Cristiano Ronaldo': 84, 'Bruno Fernandes': 85, 'Bernardo Silva': 86,
    'Rafael Leão': 84, 'Vitinha': 84, 'João Palhinha': 82,
    'Rúben Dias': 87, 'Nuno Mendes': 82, 'Diogo Costa': 84,
    # Netherlands
    'Memphis Depay': 82, 'Cody Gakpo': 83, 'Xavi Simons': 84,
    'Frenkie de Jong': 85, 'Tijjani Reijnders': 82, 'Jerdy Schouten': 80,
    'Virgil van Dijk': 86, 'Nathan Aké': 83, 'Denzel Dumfries': 81,
    # Belgium
    'Kevin De Bruyne': 87, 'Romelu Lukaku': 83, 'Jeremy Doku': 84,
    'Youri Tielemans': 82, 'Amadou Onana': 83, 'Wout Faes': 79,
    # Others
    'Erling Haaland': 91, 'Martin Ødegaard': 87, 'Alexander Sørloth': 82,
    'Robert Lewandowski': 85, 'Piotr Zieliński': 82, 'Wojciech Szczęsny': 81,
    'Luis Díaz': 85, 'James Rodríguez': 80, 'Davinson Sánchez': 80,
    'Federico Valverde': 87, 'Darwin Núñez': 83, 'Ronald Araújo': 85,
    'Khvicha Kvaratskhelia': 84, 'Georges Mikautadze': 80,
    'Viktor Gyökeres': 84, 'Alexander Isak': 85, 'Dejan Kulusevski': 83,
    'Luka Modrić': 83, 'Mateo Kovačić': 82, 'Joško Gvardiol': 86,
    'Heung-min Son': 84, 'Kim Min-jae': 83, 'Lee Kang-in': 82,
    'Takefusa Kubo': 82, 'Wataru Endō': 80, 'Kaoru Mitoma': 83,
    'Mehdi Taremi': 80, 'Sardar Azmoun': 79,
    'Hakim Ziyech': 80, 'Achraf Hakimi': 84, 'Noussair Mazraoui': 81,
    'Mohamed Salah': 88, 'Omar Marmoush': 83, 'Mohamed Abdelmonem': 77,
    'André Onana': 83, 'Vincent Aboubakar': 79,
    'Edouard Mendy': 80, 'Sadio Mané': 83, 'Ismaïla Sarr': 80,
    'Victor Osimhen': 86, 'Samuel Chukwueze': 81, 'Wilfred Ndidi': 81,
    'Serhou Guirassy': 84, 'Franck Kessié': 81, 'Seko Fofana': 80,
    'Taiwo Awoniyi': 80,
    'Santiago Giménez': 82, 'Raúl Jiménez': 79, 'Hirving Lozano': 82,
    'Giovanni Reyna': 80, 'Christian Pulisic': 83, 'Weston McKennie': 81,
    'Alphonso Davies': 84, 'Jonathan David': 83, 'Stephen Eustáquio': 79,
    'Nicolas Jackson': 82, 'Ismaila Sarr': 79,
}

# Club tier: top 5 leagues + rest
TOP5_LEAGUE_KEYWORDS = [
    'Real Madrid', 'Barcelona', 'Atlético Madrid', 'Sevilla', 'Valencia',
    'Manchester', 'Liverpool', 'Arsenal', 'Chelsea', 'Tottenham', 'Newcastle', 'Aston Villa',
    'Bayern', 'Dortmund', 'Leipzig', 'Leverkusen', 'Stuttgart', 'Frankfurt',
    'Juventus', 'Milan', 'Inter', 'Napoli', 'Roma', 'Lazio', 'Atalanta', 'Fiorentina',
    'PSG', 'Monaco', 'Lyon', 'Marseille', 'Lille', 'Nice', 'Rennes',
    'Ajax', 'PSV', 'Feyenoord',
    'Benfica', 'Porto', 'Sporting',
    'Celtic', 'Rangers',
    'Galatasaray', 'Fenerbahçe',
    'Shakhtar', 'Dynamo Kyiv',
    'Club Brugge', 'Anderlecht',
    'Köln', 'Union Berlin', 'Freiburg', 'Mainz', 'Augsburg', 'Hoffenheim', 'Wolfsburg',
    'Bologna', 'Torino', 'Udinese', 'Genoa', 'Monza', 'Empoli', 'Lecce', 'Cagliari',
    'Sassuolo', 'Verona', 'Salernitana',
    'Betis', 'Real Sociedad', 'Athletic', 'Villarreal', 'Osasuna', 'Getafe', 'Girona', 'Rayo',
    'Celta', 'Mallorca', 'Alavés', 'Las Palmas', 'Valladolid', 'Espanyol', 'Leganés',
    'Brentford', 'Brighton', 'Crystal Palace', 'Everton', 'Fulham', 'Nottingham',
    'West Ham', 'Wolves', 'Bournemouth', 'Ipswich', 'Leicester', 'Southampton',
    'Nantes', 'Toulouse', 'Strasbourg', 'Brest', 'Reims', 'Lens', 'Montpellier',
    'Le Havre', 'Angers', 'Auxerre', 'Saint-Étienne',
]


def get_club_tier(club: str) -> int:
    """Estimate club quality from name keywords"""
    club_lower = club.lower()
    for kw in TOP5_LEAGUE_KEYWORDS:
        if kw.lower() in club_lower:
            return 10
    return 0


def calculate_rating(name: str, caps: int, club: str) -> int:
    """Calculate player rating from caps + club + star override"""
    # Manual star rating override
    if name in STAR_RATINGS:
        return STAR_RATINGS[name]

    # Auto-calculate: caps experience + club tier bonus
    caps_score = min(caps / 150, 1.0) * 30  # 0-30 from caps
    club_bonus = get_club_tier(club)
    rating = 50 + caps_score + club_bonus

    # Clamp to 50-99
    return min(max(int(rating), 50), 99)


def main():
    # Load squads
    squads_path = Path(__file__).parent.parent / 'data' / 'wc_squads.json'
    with open(squads_path, 'r', encoding='utf-8') as f:
        squads = json.load(f)

    ratings = {}
    for team, players in squads.items():
        team_ratings = []
        for p in players:
            rating = calculate_rating(p['name'], p.get('caps', 0), p.get('club', ''))
            team_ratings.append({
                'name': p['name'],
                'position': p.get('position', '?'),
                'number': p.get('number', ''),
                'rating': rating,
                'caps': p.get('caps', 0),
                'club': p.get('club', ''),
            })
        ratings[team] = team_ratings

    # Sort each team by rating descending
    for team in ratings:
        ratings[team].sort(key=lambda x: x['rating'], reverse=True)

    # Save
    output = Path(__file__).parent.parent / 'data' / 'wc_player_ratings.json'
    with open(output, 'w', encoding='utf-8') as f:
        json.dump(ratings, f, indent=2, ensure_ascii=False)

    print(f'Player ratings saved to {output}')
    print(f'Teams: {len(ratings)}')
    total = sum(len(v) for v in ratings.values())
    print(f'Players: {total}')

    # Show top 5 star players
    all_players = []
    for team, players in ratings.items():
        for p in players:
            all_players.append((p['rating'], team, p['name'], p['position']))
    all_players.sort(reverse=True)

    print('\nTop 20 players by rating:')
    for r, team, name, pos in all_players[:20]:
        print(f'  {name:25s} ({team:15s})  rating={r}  pos={pos}')

    # Show each team's average rating
    print('\nTeam strength (avg rating of top 15):')
    team_strengths = []
    for team, players in ratings.items():
        top_ratings = [p['rating'] for p in players[:15]]
        avg = sum(top_ratings) / len(top_ratings)
        team_strengths.append((avg, team))
    team_strengths.sort(reverse=True)
    for avg, team in team_strengths[:10]:
        print(f'  {team:25s}: avg rating {avg:.1f}')
    print('  ...')
    for avg, team in team_strengths[-5:]:
        print(f'  {team:25s}: avg rating {avg:.1f}')


if __name__ == '__main__':
    main()
