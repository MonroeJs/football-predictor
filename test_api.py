"""测试 Understat API: getLeagueData/EPL/2025"""
import requests, json

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Accept': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
    'Referer': 'https://understat.com/league/EPL/2025',
}

url = 'https://understat.com/getLeagueData/EPL/2025'
resp = requests.get(url, headers=headers, timeout=15)
print(f'Status: {resp.status_code}')
print(f'Content-Type: {resp.headers.get("Content-Type", "?")}')
print(f'Length: {len(resp.text)}')

if resp.status_code == 200:
    try:
        data = resp.json()
        print(f'\nTop-level keys: {list(data.keys())}')
        
        if 'teams' in data:
            teams = data['teams']
            print(f'\nTeams: {type(teams).__name__}')
            if isinstance(teams, dict):
                print(f'  Number of teams: {len(teams)}')
                first_team = list(teams.values())[0]
                print(f'  First team keys: {list(first_team.keys())}')
                print(f'  First team name: {first_team.get("title", "?")}')
        
        if 'matches' in data:
            matches = data['matches']
            print(f'\nMatches: {type(matches).__name__}')
            if isinstance(matches, list):
                print(f'  Number of matches: {len(matches)}')
                if matches:
                    m = matches[0]
                    print(f'  First match keys: {list(m.keys())}')
                    print(f'  First match: {m.get("h",{}).get("title","?")} vs {m.get("a",{}).get("title","?")}')
                    # Find xG data
                    for key in m:
                        if 'x' in key.lower() or 'g' in key.lower():
                            print(f'  {key}: {m[key]}')
            
            elif isinstance(matches, dict):
                print(f'  Number of matches: {len(matches)}')
                first_id = list(matches.keys())[0]
                m = matches[first_id]
                print(f'  First match keys: {list(m.keys())}')
                
        # Print all top-level keys' types
        for k, v in data.items():
            if isinstance(v, (list, dict)):
                print(f'\n{k}: {type(v).__name__} len={len(v)}')
                if isinstance(v, list) and v:
                    if isinstance(v[0], dict):
                        print(f'  First item keys: {list(v[0].keys())[:15]}')
            elif isinstance(v, str):
                print(f'\n{k}: {v[:100]}')
            else:
                print(f'\n{k}: {type(v).__name__} = {v}')
                
    except json.JSONDecodeError as e:
        print(f'JSON parse error: {e}')
        print(f'First 500 chars: {resp.text[:500]}')
else:
    print(f'Response: {resp.text[:500]}')
