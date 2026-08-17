import unittest
import numpy as np
from analytics.s7_dataset.feature_engineering import extract_regex_value, engineer_features
from analytics.s7_dataset.labels import engineer_labels

class TestS7DatasetV2(unittest.TestCase):
    def test_regex_parsing(self):
        text = '''
        🚀 $MUSK (The Untold Story)
        EpkUue8SvNBiYW1XKPPBPKm5tPAL1mqwKqab9KwApump
        GTscore: ⭐⭐⭐☆☆
        📊 MC: $57.6K · ⏱ Age: 1m · 👪 Holders: 525
        🔟 Top10: 17% · 📦 Bundled: 4.0% · 🏁 First50: 11%
        ☢️ Jeeters: 5.8% · 🌱 Fresh: — · 🎯 Snipers: 0.0%
        🕸 9C · 24W · 18.9%
        '''
        
        self.assertEqual(extract_regex_value(r'MC:\s*\$?([\d\.]+[KM]?)', text), 57600.0)
        self.assertEqual(extract_regex_value(r'Age:\s*([\d\.]+[mhd])', text), 1.0)
        self.assertEqual(extract_regex_value(r'Holders:\s*([\d\,]+)', text), 525.0)
        self.assertEqual(extract_regex_value(r'Top10:\s*([\d\.]+)%', text), 17.0)
        self.assertEqual(extract_regex_value(r'Bundled:\s*([\d\.]+)%', text), 4.0)
        self.assertTrue(np.isnan(extract_regex_value(r'Fresh:\s*([\d\.]+%|—|-)', text)))
        
    def test_label_engineering(self):
        outcome = {
            'returned_2x': 1,
            'returned_5x': 0,
            'returned_10x': None,
            'rugged': 1,
            'max_return': 235.4
        }
        labels = engineer_labels(outcome)
        self.assertEqual(labels['Y_2x'], 1)
        self.assertEqual(labels['Y_5x'], 0)
        self.assertEqual(labels['Y_10x'], 0)
        self.assertEqual(labels['Y_rug'], 1)
        self.assertEqual(labels['label_max_return'], 235.4)
        self.assertEqual(labels['label_resolved'], 1)
        
        # Unresolved
        labels_unresolved = engineer_labels(None)
        self.assertTrue(np.isnan(labels_unresolved['Y_2x']))
        self.assertEqual(labels_unresolved['label_resolved'], 0)

if __name__ == '__main__':
    unittest.main()
