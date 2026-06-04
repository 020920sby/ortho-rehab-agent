{/* 2026-06-01: 复诊计划管理 — 完整列表 + 添加/编辑 + AI 生成 */}
import { useState, useEffect, useCallback } from 'react';
import { Calendar, MapPin, Building2, User as UserIcon, ClipboardList, AlertTriangle, Briefcase, Bell, BellOff, Plus, Trash2, Edit3, Sparkles, Loader2, ChevronLeft, Check, X } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { toast } from 'sonner';
import { usePatient } from '../App';
import { getFollowups, createFollowup, updateFollowup, deleteFollowup, generateFollowups, FollowupPlan as FollowupType } from '../../services/api';

interface FollowupPlanProps {
  onBack: () => void;
}

export function FollowupPlanPage({ onBack }: FollowupPlanProps) {
  const { patientId } = usePatient();
  const [followups, setFollowups] = useState<FollowupType[]>([]);
  const [loading, setLoading] = useState(true);
  const [showEditor, setShowEditor] = useState(false);
  const [editingFollowup, setEditingFollowup] = useState<FollowupType | null>(null);
  const [generating, setGenerating] = useState(false);

  const fetchFollowups = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getFollowups(patientId);
      setFollowups(data.followups || []);
    } catch {
      toast.error('加载复诊计划失败');
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    fetchFollowups();
  }, [fetchFollowups]);

  const handleGenerate = async () => {
    setGenerating(true);
    try {
      const result = await generateFollowups(patientId);
      toast.success(result.message || 'AI 复诊计划已生成');
      await fetchFollowups();
    } catch (e: unknown) {
      const err = e as { response?: { data?: { detail?: string } } };
      toast.error(err?.response?.data?.detail || '生成失败');
    } finally {
      setGenerating(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm('确定删除此复诊计划？')) return;
    try {
      await deleteFollowup(patientId, id);
      toast.success('已删除');
      await fetchFollowups();
    } catch {
      toast.error('删除失败');
    }
  };

  const handleToggleComplete = async (item: FollowupType) => {
    try {
      await updateFollowup(patientId, item.id, { completed: !item.completed });
      await fetchFollowups();
    } catch {
      toast.error('操作失败');
    }
  };

  const isPast = (dateStr: string) => new Date(dateStr) < new Date(new Date().toDateString());
  const isToday = (dateStr: string) => dateStr === new Date().toISOString().slice(0, 10);

  const upcoming = followups.filter(f => !f.completed && !isPast(f.followup_date));
  const past = followups.filter(f => f.completed || isPast(f.followup_date));

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#2A79E6] animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-24">
      {/* Header */}
      <div className="bg-white px-4 py-4 flex items-center justify-between shadow-sm sticky top-0 z-10">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="min-h-[44px] min-w-[44px] flex items-center justify-center">
            <ChevronLeft className="w-6 h-6 text-gray-600" />
          </button>
          <div>
            <h1 className="font-semibold text-lg">复诊计划</h1>
            <p className="text-xs text-gray-500">{followups.length} 条记录</p>
          </div>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={handleGenerate} disabled={generating}
            className="min-h-[44px] text-xs">
            {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4" />}
            <span className="ml-1">AI 生成</span>
          </Button>
          <Button size="sm" onClick={() => { setEditingFollowup(null); setShowEditor(true); }}
            className="min-h-[44px] bg-[#2A79E6] hover:bg-[#2267c7]">
            <Plus className="w-4 h-4 mr-1" />添加
          </Button>
        </div>
      </div>

      <div className="px-4 pt-4 space-y-4">
        {/* Empty state */}
        {followups.length === 0 && (
          <div className="bg-white rounded-2xl p-8 text-center shadow-sm">
            <Calendar className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 mb-2">暂无复诊计划</p>
            <p className="text-sm text-gray-400 mb-4">点击「AI 生成」自动创建标准复诊方案，或手动添加</p>
            <div className="flex gap-2 justify-center">
              <Button onClick={handleGenerate} disabled={generating}
                className="bg-[#2A79E6] hover:bg-[#2267c7]">
                {generating ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Sparkles className="w-4 h-4 mr-2" />}
                AI 生成复诊计划
              </Button>
            </div>
          </div>
        )}

        {/* Upcoming followups */}
        {upcoming.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
              <Bell className="w-4 h-4 text-[#2A79E6]" />即将到来的复诊
            </h3>
            <div className="space-y-3">
              {upcoming.map((item) => (
                <FollowupCard
                  key={item.id}
                  item={item}
                  isToday={isToday(item.followup_date)}
                  onEdit={() => { setEditingFollowup(item); setShowEditor(true); }}
                  onDelete={() => handleDelete(item.id)}
                  onToggleComplete={() => handleToggleComplete(item)}
                />
              ))}
            </div>
          </div>
        )}

        {/* Past / completed */}
        {past.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-gray-500 mb-3 flex items-center gap-2">
              <Check className="w-4 h-4" />已完成 / 已过期
            </h3>
            <div className="space-y-3 opacity-70">
              {past.map((item) => (
                <FollowupCard
                  key={item.id}
                  item={item}
                  isToday={false}
                  onEdit={() => { setEditingFollowup(item); setShowEditor(true); }}
                  onDelete={() => handleDelete(item.id)}
                  onToggleComplete={() => handleToggleComplete(item)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Editor Dialog */}
      <FollowupEditorDialog
        open={showEditor}
        onOpenChange={setShowEditor}
        followup={editingFollowup}
        patientId={patientId}
        onSaved={() => { setShowEditor(false); fetchFollowups(); }}
      />
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// 子组件：复诊卡片
// ═══════════════════════════════════════════════════════════

function FollowupCard({
  item, isToday, onEdit, onDelete, onToggleComplete,
}: {
  item: FollowupType;
  isToday: boolean;
  onEdit: () => void;
  onDelete: () => void;
  onToggleComplete: () => void;
}) {
  const dateObj = new Date(item.followup_date);
  const monthDay = `${dateObj.getMonth() + 1}月${dateObj.getDate()}日`;
  const weekDay = ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][dateObj.getDay()];
  const isPast = new Date(item.followup_date) < new Date(new Date().toDateString());
  const completed = Boolean(item.completed);

  return (
    <div className={`bg-white rounded-2xl p-4 shadow-sm border-2 transition-colors ${
      isToday ? 'border-[#2A79E6] bg-blue-50/30' :
      completed ? 'border-green-200' :
      isPast ? 'border-gray-200' : 'border-gray-100'
    }`}>
      <div className="flex items-start gap-3">
        {/* Date badge */}
        <div className={`flex-shrink-0 w-14 h-14 rounded-xl flex flex-col items-center justify-center ${
          isToday ? 'bg-[#2A79E6] text-white' :
          completed ? 'bg-[#48C774] text-white' :
          isPast ? 'bg-gray-200 text-gray-500' : 'bg-blue-50 text-[#2A79E6]'
        }`}>
          <span className="text-xs">{dateObj.getMonth() + 1}月</span>
          <span className="text-lg font-bold leading-tight">{dateObj.getDate()}</span>
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`font-semibold text-sm ${completed ? 'text-gray-400 line-through' : ''}`}>
              {item.content || '复诊'}
            </span>
            {isToday && <span className="text-xs bg-[#2A79E6] text-white px-1.5 py-0.5 rounded-full">今天</span>}
            {completed && <Check className="w-4 h-4 text-[#48C774]" />}
          </div>
          <p className="text-xs text-gray-500">{weekDay} · {monthDay}</p>
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-2 text-xs text-gray-500">
            {item.hospital && (
              <span className="flex items-center gap-1"><Building2 className="w-3 h-3" />{item.hospital}</span>
            )}
            {item.department && (
              <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{item.department}</span>
            )}
            {item.doctor_name && (
              <span className="flex items-center gap-1"><UserIcon className="w-3 h-3" />{item.doctor_name}</span>
            )}
          </div>
          {item.precautions && (
            <div className="flex items-start gap-1 mt-2 text-xs text-amber-600 bg-amber-50 rounded-lg p-2">
              <AlertTriangle className="w-3 h-3 flex-shrink-0 mt-0.5" />
              <span>{item.precautions}</span>
            </div>
          )}
          {item.materials_to_bring && (
            <div className="flex items-start gap-1 mt-1 text-xs text-gray-500">
              <Briefcase className="w-3 h-3 flex-shrink-0 mt-0.5" />
              <span>携带：{item.materials_to_bring}</span>
            </div>
          )}
          {item.reminder_enabled && (
            <div className="flex items-center gap-1 mt-1 text-xs text-blue-500">
              <Bell className="w-3 h-3" />提前 {item.reminder_before_days} 天提醒
            </div>
          )}
          <div className="text-xs text-gray-400 mt-1">
            {item.source === 'ai_generated' ? '🤖 AI 生成' : item.source === 'ocr' ? '📋 病历提取' : '✏️ 手动添加'}
          </div>
        </div>

        {/* Actions */}
        <div className="flex flex-col gap-1 flex-shrink-0">
          <button onClick={onToggleComplete}
            className={`min-h-[44px] min-w-[44px] rounded-full flex items-center justify-center ${
              completed ? 'bg-green-100 text-green-600' : 'bg-gray-100 text-gray-400 hover:bg-green-100 hover:text-green-600'
            }`}>
            {completed ? <Check className="w-4 h-4" /> : <div className="w-4 h-4 rounded-full border-2 border-current" />}
          </button>
          <button onClick={onEdit}
            className="min-h-[44px] min-w-[44px] rounded-full flex items-center justify-center text-gray-400 hover:bg-gray-100">
            <Edit3 className="w-4 h-4" />
          </button>
          <button onClick={onDelete}
            className="min-h-[44px] min-w-[44px] rounded-full flex items-center justify-center text-gray-400 hover:bg-red-50 hover:text-red-500">
            <Trash2 className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// 子组件：复诊编辑器弹窗
// ═══════════════════════════════════════════════════════════

function FollowupEditorDialog({
  open, onOpenChange, followup, patientId, onSaved,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  followup: FollowupType | null;
  patientId: string;
  onSaved: () => void;
}) {
  const isEdit = !!followup;
  const [date, setDate] = useState('');
  const [hospital, setHospital] = useState('');
  const [department, setDepartment] = useState('');
  const [doctorName, setDoctorName] = useState('');
  const [content, setContent] = useState('');
  const [precautions, setPrecautions] = useState('');
  const [materials, setMaterials] = useState('');
  const [notes, setNotes] = useState('');
  const [reminderEnabled, setReminderEnabled] = useState(false);
  const [reminderDays, setReminderDays] = useState(1);
  const [saving, setSaving] = useState(false);

  // Reset form when dialog opens
  useEffect(() => {
    if (open) {
      if (followup) {
        setDate(followup.followup_date || '');
        setHospital(followup.hospital || '');
        setDepartment(followup.department || '');
        setDoctorName(followup.doctor_name || '');
        setContent(followup.content || '');
        setPrecautions(followup.precautions || '');
        setMaterials(followup.materials_to_bring || '');
        setNotes(followup.notes || '');
        setReminderEnabled(Boolean(followup.reminder_enabled));
        setReminderDays(followup.reminder_before_days || 1);
      } else {
        // Default: 2 weeks from today
        const d = new Date(Date.now() + 14 * 86400000);
        setDate(d.toISOString().slice(0, 10));
        setHospital(''); setDepartment(''); setDoctorName(''); setContent('');
        setPrecautions(''); setMaterials(''); setNotes('');
        setReminderEnabled(true); setReminderDays(1);
      }
    }
  }, [open, followup]);

  const handleSave = async () => {
    if (!date.trim()) { toast.error('请选择复诊日期'); return; }
    setSaving(true);
    try {
      const payload = {
        followup_date: date,
        hospital, department, doctor_name: doctorName, content,
        precautions, materials_to_bring: materials, notes,
        reminder_enabled: reminderEnabled,
        reminder_before_days: reminderDays,
      };
      if (isEdit && followup) {
        await updateFollowup(patientId, followup.id, payload);
        toast.success('复诊计划已更新');
      } else {
        await createFollowup(patientId, payload);
        toast.success('复诊计划已创建');
      }
      onSaved();
    } catch {
      toast.error('保存失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Calendar className="w-5 h-5 text-[#2A79E6]" />
            {isEdit ? '编辑复诊计划' : '添加复诊计划'}
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          <div>
            <label className="text-sm font-medium mb-1 block">复诊日期 *</label>
            <Input type="date" value={date}
              onChange={(e) => setDate(e.target.value)}
              className="min-h-[44px]" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-sm font-medium mb-1 block">医院</label>
              <Input value={hospital} onChange={(e) => setHospital(e.target.value)}
                placeholder="如：市人民医院" className="min-h-[44px]" />
            </div>
            <div>
              <label className="text-sm font-medium mb-1 block">科室</label>
              <Input value={department} onChange={(e) => setDepartment(e.target.value)}
                placeholder="如：骨科" className="min-h-[44px]" />
            </div>
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">医生</label>
            <Input value={doctorName} onChange={(e) => setDoctorName(e.target.value)}
              placeholder="主治医生姓名" className="min-h-[44px]" />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">复诊内容</label>
            <Input value={content} onChange={(e) => setContent(e.target.value)}
              placeholder="如：拆线、X光复查、ROM评估" className="min-h-[44px]" />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">注意事项</label>
            <Input value={precautions} onChange={(e) => setPrecautions(e.target.value)}
              placeholder="如：复查前需空腹" className="min-h-[44px]" />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">需携带材料</label>
            <Input value={materials} onChange={(e) => setMaterials(e.target.value)}
              placeholder="如：出院小结、医保卡、既往影像" className="min-h-[44px]" />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">备注</label>
            <Input value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="其他备注信息" className="min-h-[44px]" />
          </div>

          {/* Reminder settings */}
          <div className="bg-gray-50 rounded-xl p-4 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                {reminderEnabled ? <Bell className="w-4 h-4 text-[#2A79E6]" /> : <BellOff className="w-4 h-4 text-gray-400" />}
                <span className="text-sm font-medium">复诊提醒</span>
              </div>
              <button onClick={() => setReminderEnabled(!reminderEnabled)}
                className={`w-12 h-6 rounded-full transition-colors ${reminderEnabled ? 'bg-[#2A79E6]' : 'bg-gray-300'}`}>
                <div className={`w-5 h-5 bg-white rounded-full shadow transition-transform ${
                  reminderEnabled ? 'translate-x-6' : 'translate-x-0.5'
                }`} />
              </button>
            </div>
            {reminderEnabled && (
              <div className="flex items-center gap-2">
                <span className="text-sm text-gray-500">提前</span>
                <select value={reminderDays} onChange={(e) => setReminderDays(Number(e.target.value))}
                  className="border rounded-lg px-3 py-2 text-sm min-h-[44px]">
                  {[1, 2, 3, 5, 7].map(d => (
                    <option key={d} value={d}>{d} 天</option>
                  ))}
                </select>
                <span className="text-sm text-gray-500">提醒</span>
              </div>
            )}
          </div>

          <Button onClick={handleSave} disabled={saving}
            className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12">
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
            {isEdit ? '保存修改' : '添加复诊计划'}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
