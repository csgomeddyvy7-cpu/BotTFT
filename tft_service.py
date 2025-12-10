import aiohttp
import asyncio
from datetime import datetime, timedelta
import random

class TFTService:
    """Dịch vụ lấy dữ liệu TFT"""
    
    def __init__(self):
        self.session = None
        self.cache = {}
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def close_session(self):
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def get_player_overview(self, riot_id, region='vn'):
        """
        Lấy tổng quan player
        Returns: {
            'rank': str,
            'lp': int,
            'wins': int,
            'losses': int,
            'total_games': int,
            'level': int,
            'last_played': str
        }
        """
        # Trong thực tế, bạn sẽ gọi API thực
        # Đây là mock data cho demo
        
        await asyncio.sleep(0.5)  # Simulate API delay
        
        # Tạo dữ liệu giả dựa trên Riot ID
        seed = sum(ord(c) for c in riot_id)
        random.seed(seed)
        
        ranks = ['Iron IV', 'Iron III', 'Iron II', 'Iron I',
                'Bronze IV', 'Bronze III', 'Bronze II', 'Bronze I',
                'Silver IV', 'Silver III', 'Silver II', 'Silver I',
                'Gold IV', 'Gold III', 'Gold II', 'Gold I',
                'Platinum IV', 'Platinum III', 'Platinum II', 'Platinum I',
                'Diamond IV', 'Diamond III', 'Diamond II', 'Diamond I',
                'Master', 'Grandmaster', 'Challenger']
        
        rank_index = min(seed % 100 // 4, len(ranks) - 1)
        rank = ranks[rank_index]
        
        return {
            'rank': rank,
            'lp': random.randint(0, 100),
            'wins': random.randint(10, 200),
            'losses': random.randint(10, 200),
            'total_games': random.randint(20, 400),
            'level': random.randint(30, 500),
            'last_played': (datetime.now() - timedelta(hours=random.randint(1, 72))).isoformat(),
            'source': 'mock_data'
        }
    
    async def get_match_history(self, riot_id, region='vn', limit=5):
        """
        Lấy lịch sử match
        Returns: list of match data
        """
        # Mock data - trong thực tế sẽ gọi API thật
        
        await asyncio.sleep(0.3)
        
        matches = []
        seed = sum(ord(c) for c in riot_id)
        random.seed(seed)
        
        for i in range(limit):
            placement = random.randint(1, 8)
            level = random.randint(7, 10)
            
            # Tạo traits ngẫu nhiên
            all_traits = ['Darkin', 'Challenger', 'Juggernaut', 'Shurima', 
                         'Ionia', 'Noxus', 'Sorcerer', 'Multicaster',
                         'Demacia', 'Freljord', 'Piltover', 'Zaun',
                         'Void', 'Yordle', 'Strategist', 'Gunner']
            
            num_traits = random.randint(3, 6)
            selected_traits = random.sample(all_traits, num_traits)
            
            traits = []
            for trait in selected_traits:
                traits.append({
                    'name': trait,
                    'tier': random.randint(1, 3),
                    'num_units': random.randint(2, 8)
                })
            
            # Tạo units ngẫu nhiên
            all_units = ['Aatrox', 'Kaisa', 'Warwick', 'JarvanIV', 'Nasus',
                        'Azir', 'Katarina', 'Darius', 'Swain', 'Jayce',
                        'Heimerdinger', 'Zeri', 'Jinx', 'Vi', 'Ekko']
            
            num_units = random.randint(8, 12)
            selected_units = random.sample(all_units, min(num_units, len(all_units)))
            
            units = []
            for unit in selected_units:
                units.append({
                    'character_id': unit,
                    'tier': random.randint(1, 3),
                    'items': random.sample(['BF Sword', 'Recurve Bow', 'Chain Vest'], 
                                          random.randint(0, 3))
                })
            
            matches.append({
                'match_id': f"{riot_id.replace('#', '_')}_{int(datetime.now().timestamp()) - i}",
                'placement': placement,
                'level': level,
                'traits': traits,
                'units': units,
                'timestamp': (datetime.now() - timedelta(hours=i*3)).isoformat(),
                'game_duration': random.randint(1200, 1800),
                'players_remaining': 8 if i == 0 else random.randint(1, 8),
                'source': 'mock_data'
            })
        
        return matches
    
    async def get_match_details(self, match_id):
        """Lấy chi tiết match (mock)"""
        await asyncio.sleep(0.2)
        
        return {
            'match_id': match_id,
            'info': {
                'game_datetime': datetime.now().timestamp() * 1000,
                'game_length': random.randint(1200, 1800),
                'queue_id': 1100,
                'tft_set_number': 9,
                'game_version': '13.19.123.4567'
            },
            'participants': []
        }
    
    async def get_live_rank(self, riot_id, region):
        """Lấy rank hiện tại (mock)"""
        overview = await self.get_player_overview(riot_id, region)
        return overview.get('rank', 'Unknown')
