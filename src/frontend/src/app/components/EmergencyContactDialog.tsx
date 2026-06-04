{/* 2026-06-01: 紧急联系人管理弹窗 — 最多3个，Dialog展示+编辑 */}
import { useState, useEffect } from 'react';
import { Phone, Plus, Trash2, Save, Loader2, User as UserIcon, Heart } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { toast } from 'sonner';
import { usePatient } from '../App';
import { getEmergencyContacts, saveEmergencyContacts, EmergencyContact } from '../../services/api';

interface EmergencyContactDialogProps {
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

const RELATIONSHIPS = ['配偶', '子女', '父母', '兄弟姐妹', '主治医生', '其他'];

export function EmergencyContactDialog({ open, onOpenChange }: EmergencyContactDialogProps) {
  const { patientId } = usePatient();
  const [contacts, setContacts] = useState<EmergencyContact[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState(false);

  const fetchContacts = async () => {
    setLoading(true);
    try {
      const data = await getEmergencyContacts(patientId);
      setContacts(data || []);
    } catch {
      toast.error('加载紧急联系人失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) fetchContacts();
  }, [open, patientId]);

  const handleSave = async () => {
    // 过滤空行
    const valid = contacts.filter(c => c.name.trim() || c.phone.trim());
    if (valid.length === 0) {
      toast.error('请至少填写一个联系人的姓名和电话');
      return;
    }
    setSaving(true);
    try {
      await saveEmergencyContacts(patientId, valid);
      toast.success('紧急联系人已保存');
      setEditing(false);
      fetchContacts();
    } catch {
      toast.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  const handleAdd = () => {
    if (contacts.length >= 3) {
      toast.error('最多添加3个紧急联系人');
      return;
    }
    setContacts([...contacts, { name: '', relationship: '', phone: '' }]);
  };

  const handleRemove = (index: number) => {
    setContacts(contacts.filter((_, i) => i !== index));
  };

  const handleChange = (index: number, field: keyof EmergencyContact, value: string) => {
    const updated = [...contacts];
    updated[index] = { ...updated[index], [field]: value };
    setContacts(updated);
  };

  const relationshipColor = (rel: string) => {
    if (['配偶', '子女', '父母'].includes(rel)) return 'text-red-500 bg-red-50';
    if (rel === '主治医生') return 'text-blue-500 bg-blue-50';
    return 'text-gray-500 bg-gray-100';
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Phone className="w-5 h-5 text-[#2A79E6]" />紧急联系人
          </DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="w-6 h-6 text-[#2A79E6] animate-spin" />
          </div>
        ) : (
          <div className="space-y-4 pt-2">
            {/* View mode */}
            {!editing && contacts.length > 0 && (
              <div className="space-y-3">
                {contacts.map((c, i) => (
                  <div key={i} className="bg-gray-50 rounded-xl p-4 flex items-center gap-3">
                    <div className="w-10 h-10 bg-red-100 rounded-full flex items-center justify-center">
                      <Heart className="w-5 h-5 text-red-500" />
                    </div>
                    <div className="flex-1">
                      <div className="font-medium text-sm">
                        {c.name}
                        {c.relationship && (
                          <span className={`ml-2 text-xs px-2 py-0.5 rounded-full ${relationshipColor(c.relationship)}`}>
                            {c.relationship}
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-[#2A79E6] font-medium mt-0.5">{c.phone}</div>
                    </div>
                    <a href={`tel:${c.phone}`} className="min-h-[44px] min-w-[44px] flex items-center justify-center bg-[#48C774] text-white rounded-full">
                      <Phone className="w-4 h-4" />
                    </a>
                  </div>
                ))}
                <Button variant="outline" onClick={() => setEditing(true)}
                  className="w-full min-h-[44px]">
                  编辑联系人
                </Button>
              </div>
            )}

            {/* Edit mode or empty */}
            {(editing || contacts.length === 0) && (
              <div className="space-y-4">
                {contacts.length === 0 && !editing && (
                  <div className="text-center py-6">
                    <Phone className="w-12 h-12 text-gray-300 mx-auto mb-3" />
                    <p className="text-sm text-gray-500 mb-1">暂无紧急联系人</p>
                    <p className="text-xs text-gray-400">添加紧急联系人以便在需要时快速联系</p>
                  </div>
                )}

                {contacts.map((c, i) => (
                  <div key={i} className="bg-gray-50 rounded-xl p-4 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-medium text-gray-500">联系人 {i + 1}</span>
                      <button onClick={() => handleRemove(i)}
                        className="text-red-400 hover:text-red-600 min-h-[44px] min-w-[44px] flex items-center justify-center">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                    <Input
                      value={c.name}
                      onChange={(e) => handleChange(i, 'name', e.target.value)}
                      placeholder="姓名"
                      className="min-h-[44px]"
                    />
                    <div className="grid grid-cols-2 gap-2">
                      <select
                        value={c.relationship}
                        onChange={(e) => handleChange(i, 'relationship', e.target.value)}
                        className="border rounded-lg px-3 py-2 text-sm min-h-[44px] bg-white"
                      >
                        <option value="">关系</option>
                        {RELATIONSHIPS.map(r => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                      <Input
                        value={c.phone}
                        onChange={(e) => handleChange(i, 'phone', e.target.value)}
                        placeholder="电话号码"
                        type="tel"
                        className="min-h-[44px]"
                      />
                    </div>
                  </div>
                ))}

                {contacts.length < 3 && (
                  <Button variant="outline" onClick={handleAdd}
                    className="w-full border-dashed min-h-[44px]">
                    <Plus className="w-4 h-4 mr-2" />添加联系人 ({contacts.length}/3)
                  </Button>
                )}

                <Button onClick={handleSave} disabled={saving}
                  className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12">
                  {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
                  保存联系人
                </Button>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
