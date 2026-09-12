import datetime
import math

# --- Constants ---

HEAVENLY_STEMS = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
EARTHLY_BRANCHES = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']
FIVE_ELEMENTS = ['木', '火', '土', '金', '水']
UNIVERSAL_STARS = ['比肩', '劫財', '食神', '傷官', '偏財', '正財', '偏官', '正官', '偏印', '正印']
TWELVE_FORTUNES = ['長生', '沐浴', '冠帯', '建禄', '帝旺', '衰', '病', '死', '墓', '絶', '胎', '養']

STEM_ELEMENT_MAP = {
    '甲': '木', '乙': '木',
    '丙': '火', '丁': '火',
    '戊': '土', '己': '土',
    '庚': '金', '辛': '金',
    '壬': '水', '癸': '水'
}

BRANCH_ELEMENT_MAP = {
    '子': '水', '丑': '土', '寅': '木', '卯': '木',
    '辰': '土', '巳': '火', '午': '火', '未': '土',
    '申': '金', '酉': '金', '戌': '土', '亥': '水'
}

STEM_MEANINGS = {
    '甲': {'name': '甲（こう）', 'element': '木', 'meaning': '大きな樹。成長、発展、リーダーシップを象徴。'},
    '乙': {'name': '乙（おつ）', 'element': '木', 'meaning': '柔軟な草。適応力、優雅さを象徴。'},
    '丙': {'name': '丙（へい）', 'element': '火', 'meaning': '太陽。明るさ、熱情、活力を象徴。'},
    '丁': {'name': '丁（てい）', 'element': '火', 'meaning': 'ともし火。知恵、直感、温かみを象徴。'},
    '戊': {'name': '戊（ぼ）', 'element': '土', 'meaning': '大きな山。安定、信頼、堅実さを象徴。'},
    '己': {'name': '己（き）', 'element': '土', 'meaning': '柔らかい土。包容力、柔軟性を象徴。'},
    '庚': {'name': '庚（こう）', 'element': '金', 'meaning': '鉱石。決断力、正義感を象徴。'},
    '辛': {'name': '辛（しん）', 'element': '金', 'meaning': '磨かれた金。洗練、美しさ、繊細さを象徴。'},
    '壬': {'name': '壬（じん）', 'element': '水', 'meaning': '大河。流動性、知識を象徴。'},
    '癸': {'name': '癸（き）', 'element': '水', 'meaning': '雨露。優しさ、直感を象徴。'}
}

# --- Calculation Logic ---

class FortuneEngine:
    def __init__(self):
        pass

    def calculate_stem_branch(self, year, month, day):
        # 基準点: 1900年1月31日
        base_year = 1900
        base_date = datetime.datetime(1900, 1, 31)
        try:
            target_date = datetime.datetime(year, month, day)
        except ValueError:
            target_date = datetime.datetime(year, month, 28) # 簡易的なエラー回避
        
        # 年の干支
        year_diff = year - base_year
        year_stem_idx = year_diff % 10
        year_branch_idx = year_diff % 12
        
        # 月の干支 (簡易計算)
        month_stem_idx = (year_stem_idx * 2 + month - 1) % 10
        month_branch_idx = (month - 1) % 12
        
        # 日の干支
        day_diff = (target_date - base_date).days
        day_stem_idx = day_diff % 10
        day_branch_idx = day_diff % 12
        
        return {
            "year": {"stem": HEAVENLY_STEMS[year_stem_idx], "branch": EARTHLY_BRANCHES[year_branch_idx]},
            "month": {"stem": HEAVENLY_STEMS[month_stem_idx], "branch": EARTHLY_BRANCHES[month_branch_idx]},
            "day": {"stem": HEAVENLY_STEMS[day_stem_idx], "branch": EARTHLY_BRANCHES[day_branch_idx]}
        }

    def calculate_universal_star(self, day_stem, other_stem):
        ds_idx = HEAVENLY_STEMS.index(day_stem)
        os_idx = HEAVENLY_STEMS.index(other_stem)
        diff = (os_idx - ds_idx + 10) % 10
        return UNIVERSAL_STARS[diff]

    def calculate_twelve_fortune(self, stem, branch):
        s_idx = HEAVENLY_STEMS.index(stem)
        b_idx = EARTHLY_BRANCHES.index(branch)
        f_idx = (s_idx + b_idx * 2) % 12
        return TWELVE_FORTUNES[f_idx]

    def calculate_luck_trends(self, birth_year, birth_month, birth_day):
        """過去・現在・未来の運気トレンドを計算"""
        current_year = datetime.datetime.now().year
        trends = []
        
        for year in [current_year - 1, current_year, current_year + 1]:
            year_diff = year - birth_year
            base_score = 50 + math.sin(year_diff * 0.5) * 20
            variation = math.sin(year_diff * math.pi / 6) * 15
            offset = math.cos(year_diff * math.pi / 5) * 10
            
            trends.append({
                "year": year,
                "label": "過去" if year < current_year else ("現在" if year == current_year else "未来"),
                "overall": round(max(0, min(100, base_score + variation))),
                "career": round(max(0, min(100, base_score + variation + offset))),
                "wealth": round(max(0, min(100, base_score + offset))),
                "love": round(max(0, min(100, 60 + math.sin(year_diff * 0.7) * 25))),
                "health": round(max(0, min(100, 80 - abs(math.sin(year_diff * 0.3)) * 30)))
            })
        return trends

    def get_chart(self, birth_date_str):
        """YYYY-MM-DD 形式から命式を取得"""
        if not birth_date_str: return None
        try:
            # 形式の揺れを吸収 (YYYY年MM月DD日 -> YYYY-MM-DD)
            birth_date_str = birth_date_str.replace('年', '-').replace('月', '-').replace('日', '')
            dt = datetime.datetime.strptime(birth_date_str, "%Y-%m-%d")
            sb = self.calculate_stem_branch(dt.year, dt.month, dt.day)
            
            day_stem = sb["day"]["stem"]
            
            chart = {
                "year": sb["year"],
                "month": sb["month"],
                "day": sb["day"],
                "day_master": {"stem": day_stem, "element": STEM_ELEMENT_MAP[day_stem]},
                "stars": {
                    "year": self.calculate_universal_star(day_stem, sb["year"]["stem"]),
                    "month": self.calculate_universal_star(day_stem, sb["month"]["stem"]),
                    "day": self.calculate_universal_star(day_stem, sb["day"]["stem"])
                },
                "fortunes": {
                    "year": self.calculate_twelve_fortune(sb["year"]["stem"], sb["year"]["branch"]),
                    "month": self.calculate_twelve_fortune(sb["month"]["stem"], sb["month"]["branch"]),
                    "day": self.calculate_twelve_fortune(sb["day"]["stem"], sb["day"]["branch"])
                }
            }
            
            # Element Balance
            elements_count = {"木": 0, "火": 0, "土": 0, "金": 0, "水": 0}
            for part in ["year", "month", "day"]:
                elements_count[STEM_ELEMENT_MAP[sb[part]["stem"]]] += 1
                elements_count[BRANCH_ELEMENT_MAP[sb[part]["branch"]]] += 1
            
            chart["element_scores"] = {k: min(100, v * 25) for k, v in elements_count.items()}
            
            # Yearly Trends (Past, Present, Future)
            chart["luck_trends"] = self.calculate_luck_trends(dt.year, dt.month, dt.day)
            
            chart["personality"] = STEM_MEANINGS[day_stem]["meaning"]
            
            return chart
        except Exception as e:
            print(f"Fortune Calculation Error: {e}")
            return None
