import google.generativeai as genai
from datetime import datetime

class GeminiAnalyzer:
    """Phân tích TFT với Gemini AI"""
    
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.is_enabled = bool(api_key)
        self.model = None
        
        if self.is_enabled:
            try:
                genai.configure(api_key=api_key)
                self.model = genai.GenerativeModel('gemini-2.5-flash')
                self.status = "✅ Đã kích hoạt"
            except Exception as e:
                print(f"❌ Lỗi khởi tạo Gemini: {e}")
                self.is_enabled = False
                self.status = "❌ Lỗi khởi tạo"
        else:
            self.status = "⚠️ Chưa kích hoạt (thiếu API Key)"
    
    def is_enabled(self):
        """Kiểm tra Gemini có enabled không"""
        return self.is_enabled and self.model is not None
    
    async def analyze_match(self, match_data, riot_id):
        """
        Phân tích trận đấu bằng Gemini AI
        Returns: str (phân tích) hoặc None nếu lỗi
        """
        if not self.is_enabled():
            return None
        
        try:
            # Tạo prompt
            prompt = self._create_analysis_prompt(match_data, riot_id)
            
            # Gọi Gemini API (chạy trong thread để tránh blocking)
            import asyncio
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            
            if response and response.text:
                return response.text.strip()
            else:
                return None
                
        except Exception as e:
            print(f"❌ Lỗi Gemini analysis: {e}")
            return None
    
    def _create_analysis_prompt(self, match_data, riot_id):
        """Tạo prompt phân tích"""
        placement = match_data.get('placement', 8)
        level = match_data.get('level', 0)
        traits = match_data.get('traits', [])
        units = match_data.get('units', [])
        
        # Format traits
        traits_text = ""
        for trait in traits[:8]:  # Giới hạn 8 traits
            name = trait.get('name', 'Unknown')
            tier = trait.get('tier', 1)
            num_units = trait.get('num_units', 0)
            traits_text += f"- {name}: Tier {tier} ({num_units} units)\n"
        
        # Format units
        units_text = ""
        for unit in units[:8]:  # Giới hạn 8 units
            name = unit.get('character_id', 'Unknown')
            tier = unit.get('tier', 1)
            stars = "★" * tier
            units_text += f"- {stars} {name}\n"
        
        prompt = f"""Bạn là chuyên gia phân tích TFT (Teamfight Tactics) cấp cao.
        Hãy phân tích trận đấu sau và đưa ra nhận xét bằng tiếng Việt:

        THÔNG TIN TRẬN ĐẤU:
        - Player: {riot_id}
        - Hạng: #{placement}
        - Level: {level}
        
        ĐỘI HÌNH:
        Traits đã kích hoạt:
        {traits_text if traits_text else "Không có thông tin traits"}
        
        Units chính:
        {units_text if units_text else "Không có thông tin units"}

        YÊU CẦU PHÂN TÍCH (ngắn gọn, 100-150 từ):
        1. Đánh giá kết quả (Top #{placement})
        2. Phân tích điểm mạnh/điểm yếu của đội hình
        3. Gợi ý cải thiện cho trận tiếp theo
        4. Nếu placement thấp (5-8), đề xuất 1-2 comp tương tự tốt hơn

        Lưu ý:
        - Giọng văn thân thiện, mang tính xây dựng
        - Tập trung vào yếu tố then chốt
        - Đưa ra gợi ý thực tế, khả thi
        - Không quá dài, dễ đọc
        """
        
        return prompt
    
    async def analyze_trend(self, match_history, riot_id):
        """
        Phân tích xu hướng từ lịch sử match
        """
        if not self.is_enabled() or len(match_history) < 3:
            return None
        
        try:
            # Tạo prompt phân tích trend
            placements = [m.get('placement', 8) for m in match_history]
            avg_placement = sum(placements) / len(placements)
            
            prompt = f"""Phân tích xu hướng chơi TFT và đưa ra gợi ý:

            Player: {riot_id}
            Số trận gần đây: {len(placements)}
            Các hạng: {', '.join(f'#{p}' for p in placements)}
            Hạng trung bình: {avg_placement:.1f}

            Phân tích ngắn gọn (50-100 từ):
            1. Xu hướng performance
            2. Điểm cần cải thiện
            3. 2-3 gợi ý cụ thể để cải thiện ranking

            Trả lời bằng tiếng Việt, giọng văn tích cực.
            """
            
            import asyncio
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt
            )
            
            return response.text if response and response.text else None
            
        except Exception as e:
            print(f"❌ Lỗi Gemini trend analysis: {e}")
            return None
