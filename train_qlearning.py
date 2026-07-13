"""
train_qlearning.py
==================
Lance le pipeline Curriculum complet pour l'agent Q-Learning Awele.
A executer depuis la racine du projet :
    python train_qlearning.py
"""
import sys
import os
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.dirname(__file__))

from awale.ai.qlearning import QLearningAgent, run_curriculum

if __name__ == "__main__":
    print("=" * 60)
    print("  ENTRAINEMENT Q-LEARNING AWELE - CURRICULUM COMPLET")
    print("=" * 60)
    agent = QLearningAgent()
    run_curriculum(agent)
    print("\nEntrainement termine. Modeles sauvegardes dans models/")
