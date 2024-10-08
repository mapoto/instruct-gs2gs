import os
import clip
import torch
import torch.nn as nn
import torch.nn.functional as F
from einops import rearrange
from torchvision import io
from itertools import combinations


class ClipSimilarity(nn.Module):
    def __init__(self, name: str = "ViT-L/14"):
        super().__init__()
        assert name in ("RN50", "RN101", "RN50x4", "RN50x16", "RN50x64", "ViT-B/32", "ViT-B/16", "ViT-L/14", "ViT-L/14@336px")  # fmt: skip
        self.size = {"RN50x4": 288, "RN50x16": 384, "RN50x64": 448, "ViT-L/14@336px": 336}.get(name, 224)

        self.model, _ = clip.load(name, device="cuda", download_root="./")
        self.model.eval().requires_grad_(False)

        self.register_buffer("mean", torch.tensor((0.48145466, 0.4578275, 0.40821073)).to("cuda"))
        self.register_buffer("std", torch.tensor((0.26862954, 0.26130258, 0.27577711)).to("cuda"))

    def encode_text(self, text):
        text = clip.tokenize(text, truncate=True).to(next(self.parameters()).device)
        text_features = self.model.encode_text(text)
        text_features = text_features / text_features.norm(dim=1, keepdim=True)
        return text_features

    def encode_image(self, image):  # Input images in range [0, 1].
        image = F.interpolate(image.float(), size=self.size, mode="bicubic", align_corners=False)
        image = image - rearrange(self.mean, "c -> 1 c 1 1")
        image = image / rearrange(self.std, "c -> 1 c 1 1")
        image_features = self.model.encode_image(image)
        image_features = image_features / image_features.norm(dim=1, keepdim=True)
        return image_features

    def forward(self, image_0, image_1, text_0, text_1):
        image_features_0 = self.encode_image(image_0)
        image_features_1 = self.encode_image(image_1)
        text_features_0 = self.encode_text(text_0)
        text_features_1 = self.encode_text(text_1)
        sim_0 = F.cosine_similarity(image_features_0, text_features_0)
        sim_1 = F.cosine_similarity(image_features_1, text_features_1)
        sim_direction = F.cosine_similarity(image_features_1 - image_features_0, text_features_1 - text_features_0)
        sim_image = F.cosine_similarity(image_features_0, image_features_1)
        return sim_0, sim_1, sim_direction, sim_image

    def image_similarity(self, image_0, image_1):
        image_features_0 = self.encode_image(image_0)
        image_features_1 = self.encode_image(image_1)
        return F.cosine_similarity(image_features_0, image_features_1)

    def compute_all_similarities(self, image_features):
        similarity_matrix = F.cosine_similarity(image_features.unsqueeze(1), image_features.unsqueeze(0), dim=2)
        return similarity_matrix


def load_images_from_folder(folder):
    images = []
    filenames = []
    for filename in os.listdir(folder):
        if filename.endswith(".png"):
            img = io.read_image(os.path.join(folder, filename)).unsqueeze(0)  # Add batch dimension
            images.append(img)
            filenames.append(filename)
    images_tensor = torch.cat(images).to("cuda")
    return (filenames, images_tensor)


def find_least_similar(similarity_matrix, filenames, top_n=3):
    n = similarity_matrix.shape[0]
    similarities = []
    for i in range(n):
        for j in range(i + 1, n):
            similarities.append(((filenames[i], filenames[j]), similarity_matrix[i, j].item()))
    similarities.sort(key=lambda x: x[1])  # Sort by similarity score
    return similarities[:top_n]


def main(folder_path, model_name="ViT-L/14", top_n=3):
    clip_model = ClipSimilarity("./models/" + model_name).to("cuda")
    filenames, images = load_images_from_folder(folder_path)
    image_features = clip_model.encode_image(images)
    similarity_matrix = clip_model.compute_all_similarities(image_features)
    least_similar_pairs = find_least_similar(similarity_matrix, filenames, top_n=top_n)

    for (file1, file2), score in least_similar_pairs:
        print(f"Images: {file1} and {file2} have a similarity score of {score:.4f}")


if __name__ == "__main__":
    folder_path = "/home/lucky/Desktop/for summaery/edited/stone/epoch_1/"
    main(folder_path)
