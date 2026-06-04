{/* 2026-06-01 修复：打卡与计划生成解耦，打卡仅记录数据 */}
import { useState } from 'react';
import { Slider } from './ui/slider';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Textarea } from './ui/textarea';
import { ArrowLeft, Loader2, CheckCircle, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { usePatient } from '../App';
import { submitCheckIn, refreshPlan } from '../../services/api';

interface CheckInProps {
  onBack: () => void;
}

export function CheckIn({ onBack }: CheckInProps) {
  const { patientId } = usePatient();
  const [painLevel, setPainLevel] = useState([4]);
  const [walkingAbility, setWalkingAbility] = useState('single-crutch');
  const [romInput, setRomInput] = useState('膝关节屈曲95度，伸展0度');
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [feedback, setFeedback] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const symptoms = ['小腿肿胀', '切口发红', '发热', '小腿疼痛', '关节弹响', '无法承重', '其他'];
  const painEmojis = ['😊', '🙂', '😐', '😟', '😣', '😖', '😫', '😰', '😢', '😭', '😱'];
  const painLabels = ['无痛', '轻度', '中度', '重度', '剧痛'];

  const toggleSymptom = (symptom: string) => {
    setSelectedSymptoms((prev) =>
      prev.includes(symptom) ? prev.filter((s) => s !== symptom) : [...prev, symptom]
    );
  };

  const getPainLabel = (value: number) => {
    if (value === 0) return painLabels[0];
    if (value <= 3) return painLabels[1];
    if (value <= 5) return painLabels[2];
    if (value <= 7) return painLabels[3];
    return painLabels[4];
  };

  const handleSubmit = async () => {
    try {
      setSubmitting(true);
      const result = await submitCheckIn({
        patient_id: patientId,
        pain_score: painLevel[0],
        rom: romInput,
        walking_ability: walkingAbility,
        symptoms: selectedSymptoms,
        daily_feedback: feedback,
      });
      setSubmitted(true);
      if (result.message) {
        toast.success(result.message);
      } else {
        toast.success('打卡成功！');
      }
    } catch {
      toast.error('提交失败，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const handleRefreshPlan = async () => {
    try {
      setRefreshing(true);
      await refreshPlan(patientId);
      toast.success('康复计划已更新！返回总览查看最新方案');
    } catch {
      toast.error('计划刷新失败，请稍后重试');
    } finally {
      setRefreshing(false);
    }
  };

  if (submitted) {
    return (
      <div className="min-h-screen bg-gray-50 flex flex-col items-center justify-center px-6">
        <CheckCircle className="w-16 h-16 text-[#48C774] mb-4" />
        <h2 className="text-xl font-semibold mb-2">打卡成功！</h2>
        <p className="text-sm text-gray-600 mb-6 text-center">
          数据已记录。如需更新个性化康复方案，请点击下方按钮。
        </p>
        <div className="w-full space-y-3">
          <Button onClick={handleRefreshPlan} disabled={refreshing}
            className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12">
            {refreshing ? (
              <span className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />AI生成中...</span>
            ) : (
              <span className="flex items-center gap-2"><RefreshCw className="w-4 h-4" />更新今日康复计划</span>
            )}
          </Button>
          <Button onClick={onBack} variant="outline" className="w-full h-12">
            返回总览
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="bg-white px-4 py-6 shadow-sm sticky top-0 z-10">
        <button onClick={onBack} className="flex items-center gap-2 mb-3 text-gray-600 hover:text-gray-900 min-h-[44px]">
          <ArrowLeft className="w-5 h-5" /><span>返回</span>
        </button>
        <h1 className="font-semibold text-xl mb-1">每日康复打卡</h1>
        <p className="text-sm text-gray-600">记录今日恢复情况，AI将为你自动调整康复计划</p>
      </div>

      <div className="px-4 pt-6 pb-24 space-y-6">
        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h3 className="font-semibold mb-4">今天的疼痛程度</h3>
          <div className="flex justify-center mb-4"><div className="text-6xl">{painEmojis[painLevel[0]]}</div></div>
          <Slider value={painLevel} onValueChange={setPainLevel} max={10} step={1} className="mb-4" />
          <div className="flex justify-between items-center">
            <span className="text-3xl font-bold text-[#2A79E6]">{painLevel[0]}</span>
            <span className="text-lg text-gray-600">{getPainLabel(painLevel[0])}</span>
          </div>
          <div className="flex justify-between mt-2 text-xs text-gray-400">
            <span>0 无痛</span><span>10 剧痛</span>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="font-semibold mb-4">核心康复指标</h3>
          <div>
            <label className="block text-sm mb-2">关节活动度</label>
            <Input value={romInput} onChange={(e) => setRomInput(e.target.value)} placeholder="膝关节屈曲95度，伸展0度" className="min-h-[44px]" />
          </div>
          <div>
            <label className="block text-sm mb-2">行走能力</label>
            <Select value={walkingAbility} onValueChange={setWalkingAbility}>
              <SelectTrigger className="min-h-[44px]"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="bed">卧床</SelectItem>
                <SelectItem value="walker">助行器</SelectItem>
                <SelectItem value="double-crutch">双拐辅助</SelectItem>
                <SelectItem value="single-crutch">单拐辅助</SelectItem>
                <SelectItem value="independent">自主行走</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h3 className="font-semibold mb-4">不适症状（选填）</h3>
          <div className="flex flex-wrap gap-2">
            {symptoms.map((symptom) => (
              <button key={symptom} onClick={() => toggleSymptom(symptom)}
                className={`px-4 py-2 rounded-full text-sm transition-colors min-h-[44px] ${selectedSymptoms.includes(symptom) ? 'bg-[#2A79E6] text-white' : 'bg-gray-100 text-gray-700 hover:bg-gray-200'}`}>
                {symptom}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-2xl p-5 shadow-sm">
          <h3 className="font-semibold mb-4">今天的康复感受（选填）</h3>
          <Textarea value={feedback} onChange={(e) => setFeedback(e.target.value)}
            placeholder="可以写下今天的康复感受、遇到的问题，AI会为你解答"
            className="min-h-[120px] resize-none" />
        </div>
      </div>

      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4">
        <Button onClick={handleSubmit} disabled={submitting}
          className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12 text-base">
          {submitting ? <span className="flex items-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />提交中...</span> : '提交今日打卡'}
        </Button>
        <p className="text-xs text-gray-500 text-center mt-2">提交后可点击"更新今日康复计划"，AI将根据最新数据个性化调整训练方案</p>
      </div>
    </div>
  );
}
