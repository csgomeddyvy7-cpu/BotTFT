import json
import os
from datetime import datetime, timedelta
from pathlib import Path
import copy

class Database:
    """Quản lý database JSON đơn giản"""
    
    def __init__(self, db_file='tft_tracker.json'):
        self.file_path = db_file
        self.data = self._load_database()
        
    def _load_database(self):
        """Load database từ file"""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                print(f"⚠️ Không thể đọc file {self.file_path}, tạo mới")
        
        # Cấu trúc database mặc định
        return {
            'version': '1.0',
            'players': [],
            'settings': {
                'auto_backup': True,
                'max_backups': 10,
                'last_backup': None
            },
            'metadata': {
                'created_at': datetime.now().isoformat(),
                'last_modified': datetime.now().isoformat(),
                'total_players': 0
            }
        }
    
    def _save_database(self):
        """Lưu database vào file"""
        try:
            # Cập nhật metadata
            self.data['metadata']['last_modified'] = datetime.now().isoformat()
            self.data['metadata']['total_players'] = len(self.data['players'])
            
            # Lưu file
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            # Backup nếu cần
            if self.data['settings']['auto_backup']:
                self._create_backup()
            
            return True
        except Exception as e:
            print(f"❌ Lỗi lưu database: {e}")
            return False
    
    def _create_backup(self):
        """Tạo backup database"""
        try:
            backup_dir = Path('backups')
            backup_dir.mkdir(exist_ok=True)
            
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_file = backup_dir / f'tft_tracker_backup_{timestamp}.json'
            
            with open(backup_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            
            # Xóa backups cũ nếu quá nhiều
            self._cleanup_old_backups(backup_dir)
            
            self.data['settings']['last_backup'] = timestamp
            return True
        except Exception as e:
            print(f"❌ Lỗi tạo backup: {e}")
            return False
    
    def _cleanup_old_backups(self, backup_dir, max_backups=10):
        """Xóa backups cũ"""
        try:
            backups = list(backup_dir.glob('tft_tracker_backup_*.json'))
            backups.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            if len(backups) > max_backups:
                for backup in backups[max_backups:]:
                    backup.unlink()
        except:
            pass
    
    # ========== PLAYER OPERATIONS ==========
    
    def add_player(self, player_data):
        """Thêm player mới"""
        try:
            # Kiểm tra trùng lặp
            for player in self.data['players']:
                if (player['discord_id'] == player_data['discord_id'] and 
                    player['riot_id'].lower() == player_data['riot_id'].lower()):
                    return False
            
            self.data['players'].append(player_data)
            return self._save_database()
        except Exception as e:
            print(f"❌ Lỗi thêm player: {e}")
            return False
    
    def remove_player(self, discord_id, riot_id):
        """Xóa player"""
        try:
            initial_count = len(self.data['players'])
            self.data['players'] = [
                p for p in self.data['players']
                if not (p['discord_id'] == discord_id and p['riot_id'].lower() == riot_id.lower())
            ]
            
            if len(self.data['players']) < initial_count:
                return self._save_database()
            return False
        except Exception as e:
            print(f"❌ Lỗi xóa player: {e}")
            return False
    
    def get_player_by_riot_id(self, riot_id):
        """Tìm player theo Riot ID"""
        try:
            for player in self.data['players']:
                if player['riot_id'].lower() == riot_id.lower():
                    return copy.deepcopy(player)
            return None
        except:
            return None
    
    def get_players_by_discord_id(self, discord_id):
        """Lấy tất cả players của một Discord user"""
        try:
            players = [
                copy.deepcopy(p) for p in self.data['players']
                if p['discord_id'] == discord_id
            ]
            return players
        except:
            return []
    
    def get_all_players(self):
        """Lấy tất cả players"""
        return copy.deepcopy(self.data['players'])
    
    def update_last_match(self, discord_id, riot_id, match_id, match_time=None):
        """Cập nhật match cuối cùng"""
        try:
            for player in self.data['players']:
                if (player['discord_id'] == discord_id and 
                    player['riot_id'].lower() == riot_id.lower()):
                    player['last_match_id'] = match_id
                    player['last_match_time'] = match_time or datetime.now().isoformat()
                    player['last_checked'] = datetime.now().isoformat()
                    break
            
            return self._save_database()
        except Exception as e:
            print(f"❌ Lỗi update last match: {e}")
            return False
    
    def update_setting(self, discord_id, riot_id, setting_key, setting_value):
        """Cập nhật setting"""
        try:
            for player in self.data['players']:
                if (player['discord_id'] == discord_id and 
                    player['riot_id'].lower() == riot_id.lower()):
                    if 'settings' not in player:
                        player['settings'] = {}
                    player['settings'][setting_key] = setting_value
                    break
            
            return self._save_database()
        except Exception as e:
            print(f"❌ Lỗi update setting: {e}")
            return False
    
    def update_player_info(self, discord_id, riot_id, info_key, info_value):
        """Cập nhật thông tin player"""
        try:
            for player in self.data['players']:
                if (player['discord_id'] == discord_id and 
                    player['riot_id'].lower() == riot_id.lower()):
                    player[info_key] = info_value
                    break
            
            return self._save_database()
        except Exception as e:
            print(f"❌ Lỗi update player info: {e}")
            return False
    
    def cleanup_inactive_players(self, days_inactive=30):
        """Dọn dẹp players không hoạt động"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days_inactive)
            initial_count = len(self.data['players'])
            
            self.data['players'] = [
                p for p in self.data['players']
                if 'last_checked' in p and 
                datetime.fromisoformat(p['last_checked']) > cutoff_date
            ]
            
            removed = initial_count - len(self.data['players'])
            if removed > 0:
                self._save_database()
                return removed
            return 0
        except Exception as e:
            print(f"❌ Lỗi cleanup inactive players: {e}")
            return 0
    
    def get_stats(self):
        """Lấy thống kê database"""
        return {
            'total_players': len(self.data['players']),
            'verified_players': sum(1 for p in self.data['players'] if p.get('verified')),
            'unique_users': len(set(p['discord_id'] for p in self.data['players'])),
            'database_size': os.path.getsize(self.file_path) if os.path.exists(self.file_path) else 0,
            'last_modified': self.data['metadata']['last_modified']
        }
