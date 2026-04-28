from .network import *
import os
import json
import time

class BatchManager:
    def __init__(self):
        self.filename = os.path.join(SCRIPT_DIR, "saved_profiles.json")
        self.profiles = self.load_profiles()
        
    def load_profiles(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    return json.load(f)
            except:
                return {}
        return {}
        
    def save_profiles(self):
        try:
            with open(self.filename, 'w') as f:
                json.dump(self.profiles, f, indent=4)
            return True
        except Exception as e:
            print("[BatchManager] ❌ Failed to save profiles to {}: {}".format(self.filename, e))
            return False
            
    def save_new_batch(self, name, regs_data, sess_id=None, pro_id=None, latest_exam_id=None):
        main_regs = []
        readd_regs = []
        for item in regs_data:
            if isinstance(item, (list, tuple)):
                r = int(item[0])
                s = str(item[1])
                n = item[2] if len(item) > 2 else "Unknown"
                if str(s) == str(sess_id): main_regs.append([r, s, n])
                else: readd_regs.append([r, s, n])
            else:
                main_regs.append([int(item), str(sess_id or "AUTO"), "Unknown"])
        
        # Sort each group by registration number
        main_regs.sort(key=lambda x: x[0])
        readd_regs.sort(key=lambda x: x[0])
        
        self.profiles[name] = {
            "regs": main_regs + readd_regs,
            "sess_id": sess_id,
            "pro_id": pro_id,
            "latest_exam_id": latest_exam_id
        }
        self.save_profiles()
        
    def update_batch_info(self, name, sess_id=None, pro_id=None, latest_exam_id=None):
        if name in self.profiles:
            if sess_id: self.profiles[name]["sess_id"] = sess_id
            if pro_id: self.profiles[name]["pro_id"] = pro_id
            if latest_exam_id: self.profiles[name]["latest_exam_id"] = latest_exam_id
            self.save_profiles()
            
    def add_to_batch(self, name, regs_data):
        if name in self.profiles:
            current = self.profiles[name].get("regs", [])
            # Convert if old format
            if current and not isinstance(current[0], list):
                s_id = self.profiles[name].get("sess_id", "AUTO")
                current = [[r, s_id, "Unknown"] for r in current]
            
            # lookup by reg number
            lookup = {}
            for item in current:
                reg = str(item[0])
                if len(item) == 2: item.append("Unknown") # Ensure it has name
                lookup[reg] = item[1:] # Store [sess, name]
                
            for item in regs_data:
                if isinstance(item, (list, tuple)):
                    r_val = str(item[0])
                    s_val = item[1]
                    n_val = item[2] if len(item) > 2 else (lookup.get(r_val, ["AUTO", "Unknown"])[1])
                else:
                    r_val = str(item)
                    s_val = self.profiles[name].get("sess_id", "AUTO")
                    n_val = lookup.get(r_val, ["AUTO", "Unknown"])[1]
                lookup[r_val] = [s_val, n_val]
            
            # update and re-sort (Main first, then Re-adds)
            sess_id = self.profiles[name].get("sess_id")
            m_list = []
            r_list = []
            for r, v in lookup.items():
                item = [int(r), str(v[0]), str(v[1])]
                if str(v[0]) == str(sess_id): m_list.append(item)
                else: r_list.append(item)
            
            # Sort each group by registration number
            m_list.sort(key=lambda x: x[0])
            r_list.sort(key=lambda x: x[0])
            
            self.profiles[name]["regs"] = m_list + r_list
            self.save_profiles()
            
    def remove_from_batch(self, name, rs_rem):
        if name in self.profiles:
            curr = self.profiles[name].get("regs", [])
            if not curr: return
            if isinstance(curr[0], list):
                self.profiles[name]["regs"] = [i for i in curr if i[0] not in rs_rem]
            else:
                self.profiles[name]["regs"] = [r for r in curr if r not in rs_rem]
            self.save_profiles()
            
    def delete_batch(self, name):
        if name in self.profiles:
            del self.profiles[name]
            self.save_profiles()

batch_manager = BatchManager()

class MetaCacheManager:
    def __init__(self):
        self.filename = os.path.join(SCRIPT_DIR, "system_cache.json")
        self.ttl = 86400  # 24 hours
        
    def get_cache(self):
        if os.path.exists(self.filename):
            try:
                with open(self.filename, 'r') as f:
                    data = json.load(f)
                    if time.time() - data.get("timestamp", 0) < self.ttl:
                        return data.get("programs"), data.get("sessions")
            except: pass
        return None, None
        
    def set_cache(self, programs, sessions):
        try:
            with open(self.filename, 'w') as f:
                json.dump({
                    "timestamp": time.time(),
                    "programs": programs,
                    "sessions": sessions
                }, f)
        except: pass

meta_cache = MetaCacheManager()

