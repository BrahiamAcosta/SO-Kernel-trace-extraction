import torch
import torch.nn as nn

class IOPatternClassifier(nn.Module):
    def __init__(self, input_size=5, hidden_size=16, num_classes=3):
        super(IOPatternClassifier, self).__init__()
        
        # Red de 3 capas extremadamente ligera
        self.fc1 = nn.Linear(input_size, hidden_size)
        self.relu1 = nn.ReLU()
        self.dropout = nn.Dropout(0.2)
        
        self.fc2 = nn.Linear(hidden_size, hidden_size // 2)
        self.relu2 = nn.ReLU()
        
        self.fc3 = nn.Linear(hidden_size // 2, num_classes)
        
    def forward(self, x):
        x = self.fc1(x)
        x = self.relu1(x)
        x = self.dropout(x)
        
        x = self.fc2(x)
        x = self.relu2(x)
        
        x = self.fc3(x)
        return x  # Logits (sin softmax para CrossEntropyLoss)