# 🤖 TFT Auto Tracker Bot

Bot Discord tự động theo dõi và thông báo trận đấu TFT với xác thực 2 bước.

## ✨ Tính năng

- ✅ **Xác thực 2 bước** với Riot ID (Username#Tagline)
- 🔄 **Tự động thông báo** khi player hoàn thành trận TFT
- 🤖 **Phân tích AI** bằng Gemini 1.5 Flash (tùy chọn)
- 📊 **Database** lưu trữ thông tin players
- ⚙️ **Cài đặt linh hoạt** cho từng player

## 🚀 Triển khai

### 1. Chuẩn bị API Keys

1. **Discord Bot Token**: Tạo tại [Discord Developer Portal](https://discord.com/developers/applications)
2. **Riot API Key** (tùy chọn): Lấy tại [Riot Developer Portal](https://developer.riotgames.com/)
3. **Gemini API Key** (tùy chọn): Lấy tại [Google AI Studio](https://makersuite.google.com/app/apikey)

### 2. Deploy lên Render.com

1. Fork repo này lên GitHub
2. Đăng nhập [Render.com](https://render.com)
3. Tạo new Web Service
4. Connect GitHub repo
5. Thêm biến môi trường:
