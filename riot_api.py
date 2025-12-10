import aiohttp
import asyncio
import re
from datetime import datetime

class RiotAPI:
    """Class lấy dữ liệu thực từ Tracker.gg và OP.GG"""
    
    def __init__(self):
        self.session = None
        self.cache = {}
    
    async def get_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def get_tft_rank_vietnamese(self, riot_id, region='vn'):
        """
        Lấy rank TFT bằng tiếng Việt
        Returns: {'rank': 'Vàng II', 'lp': 75, 'source': 'tracker.gg'}
        """
        try:
            if '#' not in riot_id:
                return None
            
            username, tagline = riot_id.split('#', 1)
            
            # Thử Tracker.gg trước
            rank_data = await self._get_from_tracker_gg(username, tagline, region)
            if rank_data:
                return rank_data
            
            # Thử OP.GG
            rank_data = await self._get_from_op_gg(username, tagline, region)
            if rank_data:
                return rank_data
            
            return None
            
        except Exception as e:
            print(f"Lỗi get_tft_rank: {e}")
            return None
    
    async def _get_from_tracker_gg(self, username, tagline, region):
        """Lấy rank từ Tracker.gg"""
        try:
            import urllib.parse
            encoded_username = urllib.parse.quote(username)
            
            # URL Tracker.gg
            url = f"https://tracker.gg/tft/profile/riot/{encoded_username}%23{tagline}/overview"
            
            session = await self.get_session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'vi,en-US;q=0.7,en;q=0.3',
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Tìm rank trong HTML
                    # Tracker.gg thường có cấu trúc: <span class="stat__value">Gold II</span>
                    rank_patterns = [
                        r'<span[^>]*class="[^"]*stat__value[^"]*"[^>]*>([^<]+)</span>',
                        r'<div[^>]*class="[^"]*rating[^"]*"[^>]*>([^<]+)</div>',
                        r'Rank[^>]*>([^<]+)<',
                        r'Tier[^>]*>([^<]+)<'
                    ]
                    
                    for pattern in rank_patterns:
                        matches = re.findall(pattern, html, re.IGNORECASE)
                        for match in matches:
                            rank_text = match.strip()
                            if any(word in rank_text.lower() for word in ['iron', 'bronze', 'silver', 'gold', 'platinum', 'diamond', 'master', 'grandmaster', 'challenger']):
                                # Chuyển sang tiếng Việt
                                vietnamese_rank = self._translate_rank_to_vietnamese(rank_text)
                                return {
                                    'rank': vietnamese_rank,
                                    'source': 'tracker.gg',
                                    'raw': rank_text
                                }
            
            return None
            
        except Exception as e:
            print(f"Lỗi tracker.gg: {e}")
            return None
    
    async def _get_from_op_gg(self, username, tagline, region):
        """Lấy rank từ OP.GG"""
        try:
            # OP.GG dùng format: username-tagline
            formatted_username = username.replace(' ', '%20')
            url = f"https://www.op.gg/summoners/{region}/{formatted_username}-{tagline}"
            
            session = await self.get_session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            
            async with session.get(url, headers=headers, timeout=10) as response:
                if response.status == 200:
                    html = await response.text()
                    
                    # Tìm rank TFT trong HTML
                    # OP.GG thường có: <div class="tier-rank">Gold II</div>
                    rank_patterns = [
                        r'<div[^>]*class="[^"]*tier-rank[^"]*"[^>]*>([^<]+)</div>',
                        r'<span[^>]*class="[^"]*rank[^"]*"[^>]*>([^<]+)</span>',
                        r'TFT[^>]*>([^<]+)<'
                    ]
                    
                    for pattern in rank_patterns:
                        matches = re.findall(pattern, html, re.IGNORECASE)
                        for match in matches:
                            rank_text = match.strip()
                            if rank_text and len(rank_text) < 20:  # Tránh lấy nhầm
                                vietnamese_rank = self._translate_rank_to_vietnamese(rank_text)
                                return {
                                    'rank': vietnamese_rank,
                                    'source': 'op.gg',
                                    'raw': rank_text
                                }
            
            return None
            
        except Exception as e:
            print(f"Lỗi op.gg: {e}")
            return None
    
    def _translate_rank_to_vietnamese(self, rank_text):
        """Chuyển rank tiếng Anh sang tiếng Việt"""
        rank_text = rank_text.lower()
        
        translations = {
            'iron': 'Sắt',
            'bronze': 'Đồng',
            'silver': 'Bạc',
            'gold': 'Vàng',
            'platinum': 'Bạch Kim',
            'diamond': 'Kim Cương',
            'master': 'Cao Thủ',
            'grandmaster': 'Đại Cao Thủ',
            'challenger': 'Thách Đấu'
        }
        
        for eng, viet in translations.items():
            if eng in rank_text:
                # Giữ lại số la mã hoặc số
                import re
                tier_match = re.search(r'[IVXLCDM]+|\d+', rank_text, re.IGNORECASE)
                tier = tier_match.group() if tier_match else ''
                
                return f'{viet} {tier}'.strip()
        
        return rank_text.title()
