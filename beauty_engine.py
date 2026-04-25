import cv2
import mediapipe as mp
import numpy as np
import requests
import matplotlib.pyplot as plt
from PIL import Image
from io import BytesIO
import math
import japanize_matplotlib

class BeautyEngine:
    def __init__(self):
        # 3D顔認識 (MediaPipe)
        self.mp_face_mesh = mp.solutions.face_mesh
        self.face_mesh = self.mp_face_mesh.FaceMesh(
            static_image_mode=True,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5
        )
        # 2D顔認識 (OpenCV Cascade)
        self.anime_cascade = cv2.CascadeClassifier('lbpcascade_animeface.xml')
        # 被写体占有率 (MediaPipe)
        self.segmentation = mp.solutions.selfie_segmentation.SelfieSegmentation(model_selection=0)

    def download_image(self, url):
        response = requests.get(url)
        img = Image.open(BytesIO(response.content))
        return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

    def calculate_face_occupancy(self, image, is_2d=False):
        """顔が画面のどれくらいを占めているか(0.0-1.0)を算出"""
        if is_2d:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
            faces = self.anime_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
            if len(faces) == 0: return 0.0
            (x, y, w_f, h_f) = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)[0]
            occupancy = (w_f * h_f) / (image.shape[0] * image.shape[1])
            return round(float(occupancy), 3)
        else:
            results = self.face_mesh.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
            if not results.multi_face_landmarks:
                return 0.0
            landmarks = results.multi_face_landmarks[0].landmark
            x_coords = [l.x for l in landmarks]
            y_coords = [l.y for l in landmarks]
            # normalized coordinates so area is x_range * y_range
            face_w = max(x_coords) - min(x_coords)
            face_h = max(y_coords) - min(y_coords)
            occupancy = face_w * face_h
            return round(float(occupancy), 3)

    def analyze_3d_face(self, image):
        """実写顔の対称性とネオテニー度を計算"""
        results = self.face_mesh.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
        if not results.multi_face_landmarks:
            return None

        landmarks = results.multi_face_landmarks[0].landmark
        h, w, _ = image.shape

        # 対称性の計算 (簡略化: 左右の目の中心のY座標の差、口角のY座標の差など)
        # ランドマークID: 左目(33), 右目(263), 鼻先(1), 右口角(61), 左口角(291)
        left_eye = np.array([landmarks[33].x, landmarks[33].y])
        right_eye = np.array([landmarks[263].x, landmarks[263].y])
        
        # 左右対称性スコア (0-100) -> ズレが少ないほど高得点
        y_diff = abs(left_eye[1] - right_eye[1])
        symmetry_score = max(0, 100 - (y_diff * 500)) # 係数は調整

        # ネオテニー度 (顔面積に対する目の大きさ)
        # 目の領域を囲むポリゴン面積
        eye_indices = [33, 160, 158, 133, 153, 144] # 左目の一周
        eye_points = np.array([[landmarks[i].x * w, landmarks[i].y * h] for i in eye_indices], dtype=np.int32)
        eye_area = cv2.contourArea(eye_points)
        
        # 実際の顔の面積をランドマークから算出
        x_coords = [l.x * w for l in landmarks]
        y_coords = [l.y * h for l in landmarks]
        face_area = (max(x_coords) - min(x_coords)) * (max(y_coords) - min(y_coords))
        
        # 顔面積に対する目の面積の比率をベースにネオテニー度を調整（基準値を引き上げ）
        neoteny_score = min(100, (eye_area / face_area) * 7500) # 係数は調整(従来より大幅アップ)

        return {
            "symmetry": round(symmetry_score, 2),
            "neoteny": round(neoteny_score, 2)
        }

    def analyze_2d_face(self, image):
        """アニメ顔の検出と簡易スコアリング"""
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        faces = self.anime_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
        
        if len(faces) == 0:
            return None
        
        # 最も大きい顔を採用
        (x, y, w_f, h_f) = sorted(faces, key=lambda f: f[2]*f[3], reverse=True)[0]
        
        # 2Dは作画上対称性が高いため固定高スコアか、作画崩れ判定を入れる（今回は基本高く設定）
        symmetry_score = 95.0 + np.random.uniform(0, 5) 

        # ネオテニー度 (2Dは目が異常に大きいため高く出る)
        eye_face_ratio = (w_f * h_f) / (image.shape[0] * image.shape[1])
        neoteny_score = min(100, (eye_face_ratio * 300)) # 2D補正

        return {
            "symmetry": round(symmetry_score, 2),
            "neoteny": round(neoteny_score, 2)
        }

    def calculate_beauty_index(self, scores, proportion_data=None):
        """
        総合点算出。
        scores: {symmetry, neoteny}
        proportion_data: {whr, bmi_closeness} (3Dのみ)
        """
        s = scores['symmetry']
        n = scores['neoteny']
        
        # プロポーションスコア (無い場合はデフォルト平均)
        p = 80.0
        if proportion_data:
            whr_score = max(0, 100 - abs(proportion_data['whr'] - 0.7) * 500)
            p = whr_score
            
        # 性的二型・コントラストは、今回は簡略化してベーススコア
        sd = 85.0
        
        # 総合点 (重み付け)
        total = (s * 0.3) + (n * 0.2) + (p * 0.3) + (sd * 0.2)
        return round(total, 2)

    def generate_radar_chart(self, scores_3d, scores_2d, output_path="radar_chart.png"):
        """2Dと3Dのスコアを比較するレーダーチャートを生成"""
        labels = ["左右対称性", "若返り指数", "プロポーション", "性的二型", "社会的評価"]
        num_vars = len(labels)

        # ダミースコア補完 (実装済み以外の項目)
        def pad_scores(s):
            return [
                s.get('symmetry', 70),
                s.get('neoteny', 70),
                s.get('proportion', 80),
                s.get('dimorphism', 85),
                s.get('social_meme', 75)
            ]

        stats_3d = pad_scores(scores_3d)
        stats_2d = pad_scores(scores_2d)

        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        stats_3d += stats_3d[:1]
        stats_2d += stats_2d[:1]
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        
        # 3D
        ax.fill(angles, stats_3d, color='blue', alpha=0.25, label='3D (Actual)')
        ax.plot(angles, stats_3d, color='blue', linewidth=2)
        
        # 2D
        ax.fill(angles, stats_2d, color='red', alpha=0.25, label='2D (Anime)')
        ax.plot(angles, stats_2d, color='red', linewidth=2)

        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_thetagrids(np.degrees(angles[:-1]), labels)
        ax.set_ylim(0, 100)
        plt.legend(loc='upper right', bbox_to_anchor=(0.1, 0.1))
        
        plt.savefig(output_path)
        plt.close()
        return output_path

    def generate_single_radar_chart(self, scores, output_path="radar_chart.png"):
        """1人のスコアをプロットするレーダーチャートを生成"""
        labels = ["左右対称性", "若返り指数", "プロポーション", "性的二型", "社会的評価"]
        num_vars = len(labels)

        # ダミースコア補完
        def pad_scores(s):
            return [
                s.get('symmetry', 70),
                s.get('neoteny', 70),
                s.get('proportion', 80),
                s.get('dimorphism', 85),
                s.get('social_meme', 75)
            ]

        stats = pad_scores(scores)
        angles = np.linspace(0, 2 * np.pi, num_vars, endpoint=False).tolist()
        
        stats += stats[:1]
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(6, 6), subplot_kw=dict(polar=True))
        
        ax.fill(angles, stats, color='#ff69b4', alpha=0.4, label='対象人物')
        ax.plot(angles, stats, color='#ff69b4', linewidth=2)

        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_thetagrids(np.degrees(angles[:-1]), labels)
        ax.set_ylim(0, 100)
        
        plt.savefig(output_path)
        plt.close()
        return output_path
