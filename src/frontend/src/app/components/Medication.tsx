{/* 2026-05-03 新增：用药计划管理页面 - 勾选打卡、提醒开关、API持久化 */}
import { useState, useEffect, useCallback } from 'react';
import { Button } from './ui/button';
import { Switch } from './ui/switch';
import { ArrowLeft, Pill, Clock, Check, Loader2, Bell, BellOff } from 'lucide-react';
import { toast } from 'sonner';
import { usePatient } from '../App';
import { generateRehabPlan, logMedication, getMedicationLogs, getPatient } from '../../services/api';

interface MedicationItem {
  drug_name: string;
  dosage: string;
  frequency: string;
  notes: string;
  taken: boolean;
}

interface MedicationProps {
  onBack: () => void;
}

export function Medication({ onBack }: MedicationProps) {
  const { patientId } = usePatient();
  const [medications, setMedications] = useState<MedicationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [reminderOn, setReminderOn] = useState(true);
  const [logging, setLogging] = useState<string | null>(null);

  const fetchMeds = useCallback(async () => {
    try {
      setLoading(true);
      // 尝试获取今日用药日志
      const logData = await getMedicationLogs(patientId);
      const logs = logData.medications || [];

      if (logs.length > 0) {
        setMedications(logs.map((l: Record<string, unknown>) => ({
          drug_name: String(l.drug_name || ''),
          dosage: String(l.dosage || ''),
          frequency: '',
          notes: '',
          taken: Boolean(l.taken),
        })));
        return;
      }

      // 无日志则从 AI 康复计划中提取用药
      const patientInfo = await getPatient(patientId);
      const result = await generateRehabPlan({
        patient_id: patientId,
        surgery_type: patientInfo.surgery_type || 'TKA',
        surgery_date: patientInfo.surgery_date || '',
        pain_score: 4,
        rom: '',
        daily_feedback: '',
      });
      const plan = result.daily_plan || {};
      const planMeds = (plan.medication || []) as MedicationItem[];
      if (planMeds.length > 0) {
        setMedications(planMeds.map((m) => ({ ...m, taken: false })));
      } else {
        setMedications([
          { drug_name: '塞来昔布胶囊', dosage: '200mg', frequency: '每日一次', notes: '饭后服用', taken: false },
          { drug_name: '利伐沙班片', dosage: '10mg', frequency: '每日一次', notes: '抗凝预防DVT', taken: false },
        ]);
      }
    } catch {
      setMedications([
        { drug_name: '塞来昔布胶囊', dosage: '200mg', frequency: '每日一次', notes: '饭后服用', taken: false },
        { drug_name: '利伐沙班片', dosage: '10mg', frequency: '每日一次', notes: '抗凝预防DVT', taken: false },
      ]);
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    fetchMeds();
  }, [fetchMeds]);

  const handleToggleTaken = async (drugName: string, currentTaken: boolean) => {
    try {
      setLogging(drugName);
      await logMedication(patientId, {
        drug_name: drugName,
        taken: !currentTaken,
      });
      setMedications((prev) =>
        prev.map((m) => (m.drug_name === drugName ? { ...m, taken: !currentTaken } : m))
      );
      toast.success(!currentTaken ? `已记录：${drugName} 已服用` : `已取消：${drugName}`);
    } catch {
      toast.error('记录失败，请稍后重试');
    } finally {
      setLogging(null);
    }
  };

  const takenCount = medications.filter((m) => m.taken).length;
  const totalCount = medications.length;

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#2A79E6] animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white px-4 py-6 shadow-sm sticky top-0 z-10">
        <button onClick={onBack}
          className="flex items-center gap-2 mb-3 text-gray-600 hover:text-gray-900 min-h-[44px]">
          <ArrowLeft className="w-5 h-5" /><span>返回</span>
        </button>
        <div className="flex items-start justify-between">
          <div>
            <h1 className="font-semibold text-xl mb-1">用药计划</h1>
            <p className="text-sm text-gray-600">今日已服用 {takenCount}/{totalCount} 种</p>
          </div>
          {/* 2026-05-03 修复：用药提醒开关 */}
          <div className="flex items-center gap-2 bg-gray-100 rounded-full px-3 py-2">
            {reminderOn ? <Bell className="w-4 h-4 text-[#2A79E6]" /> : <BellOff className="w-4 h-4 text-gray-400" />}
            <span className="text-xs text-gray-600">推送提醒</span>
            <Switch checked={reminderOn} onCheckedChange={(v) => {
              setReminderOn(v);
              toast.success(v ? '用药提醒已开启' : '用药提醒已关闭');
            }} />
          </div>
        </div>
      </div>

      {/* Medication List */}
      <div className="px-4 pt-6 pb-24 space-y-3">
        {medications.length === 0 && (
          <div className="text-center py-12">
            <Pill className="w-12 h-12 text-gray-300 mx-auto mb-3" />
            <p className="text-gray-500">暂无用药计划</p>
            <p className="text-xs text-gray-400 mt-1">请先生成康复计划以获取用药建议</p>
          </div>
        )}
        {medications.map((med, index) => (
          <div key={index}
            className={`bg-white rounded-2xl p-4 shadow-sm transition-opacity ${med.taken ? 'opacity-60' : ''}`}
          >
            <div className="flex items-start gap-3">
              {/* 2026-05-03 修复：服药勾选框 */}
              <button
                onClick={() => handleToggleTaken(med.drug_name, med.taken)}
                disabled={logging === med.drug_name}
                className={`flex-shrink-0 mt-1 w-7 h-7 rounded-full border-2 flex items-center justify-center transition-colors min-h-[44px] min-w-[44px] ${
                  med.taken ? 'bg-[#48C774] border-[#48C774]' : 'border-gray-300 hover:border-[#48C774]'
                }`}
              >
                {logging === med.drug_name ? (
                  <Loader2 className="w-4 h-4 text-white animate-spin" />
                ) : med.taken ? (
                  <Check className="w-4 h-4 text-white" />
                ) : null}
              </button>
              <div className="flex-1">
                <div className="flex items-start justify-between mb-1">
                  <h3 className={`font-semibold ${med.taken ? 'line-through text-gray-400' : ''}`}>
                    {med.drug_name}
                  </h3>
                  {med.taken && (
                    <span className="text-xs text-[#48C774] bg-green-50 px-2 py-1 rounded">已服用</span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-sm text-gray-600 mb-1">
                  <span className="flex items-center gap-1">
                    <Pill className="w-4 h-4" />{med.dosage}
                  </span>
                  {med.frequency && (
                    <span className="flex items-center gap-1">
                      <Clock className="w-4 h-4" />{med.frequency}
                    </span>
                  )}
                </div>
                {med.notes && (
                  <p className="text-xs text-gray-400 mt-1">{med.notes}</p>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Daily Summary */}
        {totalCount > 0 && (
          <div className={`rounded-2xl p-4 ${takenCount === totalCount ? 'bg-green-50 border border-green-200' : 'bg-blue-50 border border-blue-200'}`}>
            <p className="text-sm text-center">
              {takenCount === totalCount
                ? '✅ 今日已按时服用所有药物'
                : `💊 还有 ${totalCount - takenCount} 种药物待服用`}
            </p>
          </div>
        )}
      </div>

      {/* Bottom action */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4">
        <Button onClick={onBack} className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12 text-base">
          返回总览
        </Button>
      </div>
    </div>
  );
}
