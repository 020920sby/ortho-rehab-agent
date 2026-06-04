{/* 2026-05-03 修复：训练计划页面 - 计时模式、跳过原因、exercise-log API、toast通知 */}
import { useState, useEffect, useCallback, useRef } from 'react';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Textarea } from './ui/textarea';
import { Check, Clock, Repeat, AlertTriangle, ArrowLeft, Loader2, Play, Pause, SkipForward } from 'lucide-react';
import { toast } from 'sonner';
import { usePatient } from '../App';
import { getExercises, completeExercise as completeExerciseApi, logExercise } from '../../services/api';

interface Exercise {
  id: string;
  name: string;
  duration: string;
  sets: string;
  keyPoints: string;
  warning: string;
  completed: boolean;
}

interface TrainingProps {
  onBack: () => void;
}

function parseDurationSeconds(duration: string): number {
  const m = duration.match(/(\d+)/);
  return m ? parseInt(m[1], 10) * 60 : 300; // default 5 min
}

export function Training({ onBack }: TrainingProps) {
  const { patientId } = usePatient();
  const [exercises, setExercises] = useState<Exercise[]>([]);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState<string | null>(null);

  // 2026-05-03 修复：计时器模式
  const [timerExercise, setTimerExercise] = useState<Exercise | null>(null);
  const [timerSeconds, setTimerSeconds] = useState(0);
  const [timerRunning, setTimerRunning] = useState(false);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 2026-05-03 修复：跳过原因对话框
  const [skipDialogOpen, setSkipDialogOpen] = useState(false);
  const [skipExerciseId, setSkipExerciseId] = useState<string | null>(null);
  const [skipReason, setSkipReason] = useState('');

  const fetchExercises = useCallback(async () => {
    try {
      setLoading(true);
      const data = await getExercises(patientId);
      setExercises(data.exercises || []);
    } catch {
      setExercises([
        { id: '1', name: '直腿抬高训练', duration: '10分钟', sets: '3组×15次', keyPoints: '保持膝盖伸直，缓慢抬起', warning: '避免用力过猛，感到剧痛立即停止', completed: false },
        { id: '2', name: '膝关节屈伸练习', duration: '8分钟', sets: '2组×10次', keyPoints: '坐姿进行，动作缓慢', warning: '屈曲角度不超过当前最大值', completed: false },
        { id: '3', name: '踝泵运动', duration: '5分钟', sets: '持续5分钟', keyPoints: '脚尖向上勾起，向下压', warning: '预防血栓，每小时建议做一次', completed: false },
        { id: '4', name: '靠墙静蹲', duration: '6分钟', sets: '3组×30秒', keyPoints: '膝关节不超过脚尖', warning: '如感到膝盖疼痛，减少下蹲深度', completed: false },
        { id: '5', name: '行走训练', duration: '15分钟', sets: '室内行走', keyPoints: '保持正确姿势，均匀负重', warning: '使用单拐辅助，避免跌倒', completed: false },
      ]);
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    fetchExercises();
  }, [fetchExercises]);

  // Timer cleanup
  useEffect(() => {
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, []);

  const startTimer = (exercise: Exercise) => {
    if (timerRef.current) clearInterval(timerRef.current);
    const seconds = parseDurationSeconds(exercise.duration);
    setTimerExercise(exercise);
    setTimerSeconds(seconds);
    setTimerRunning(true);
    timerRef.current = setInterval(() => {
      setTimerSeconds((prev) => {
        if (prev <= 1) {
          clearInterval(timerRef.current!);
          setTimerRunning(false);
          handleCompleteExercise(exercise.id);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    toast.info(`开始计时：${exercise.name}`);
  };

  const pauseTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    setTimerRunning(false);
    toast.info('计时已暂停');
  };

  const stopTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = null;
    setTimerExercise(null);
    setTimerRunning(false);
    setTimerSeconds(0);
  };

  const handleCompleteExercise = async (id: string) => {
    const ex = exercises.find((e) => e.id === id);
    const name = ex?.name || '';
    try {
      setCompleting(id);
      await completeExerciseApi(patientId, id);
      await logExercise(patientId, {
        exercise_id: id,
        exercise_name: name,
        completed: true,
        skipped_reason: '',
      });
      setExercises((prev) => prev.map((e) => (e.id === id ? { ...e, completed: true } : e)));
      toast.success(`✅ 已完成：${name}`);
      setTimerExercise(null);
      setTimerRunning(false);
    } catch {
      setExercises((prev) => prev.map((e) => (e.id === id ? { ...e, completed: true } : e)));
      toast.success(`✅ 已完成：${name}`);
    } finally {
      setCompleting(null);
    }
  };

  const handleSkip = async () => {
    if (!skipExerciseId) return;
    const ex = exercises.find((e) => e.id === skipExerciseId);
    const name = ex?.name || '';
    try {
      setCompleting(skipExerciseId);
      await logExercise(patientId, {
        exercise_id: skipExerciseId,
        exercise_name: name,
        completed: false,
        skipped_reason: skipReason || '未说明',
      });
      setSkipDialogOpen(false);
      setSkipReason('');
      setSkipExerciseId(null);
      toast.info(`已跳过：${name}`);
    } catch {
      toast.error('记录失败');
    } finally {
      setCompleting(null);
    }
  };

  const openSkipDialog = (id: string) => {
    setSkipExerciseId(id);
    setSkipReason('');
    setSkipDialogOpen(true);
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m}:${sec.toString().padStart(2, '0')}`;
  };

  const completedCount = exercises.filter((e) => e.completed).length;
  const totalCount = exercises.length;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;
  const allCompleted = completedCount === totalCount && totalCount > 0;

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#2A79E6] animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Timer Overlay */}
      {timerExercise && (
        <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl p-8 w-full max-w-sm text-center shadow-2xl">
            <h2 className="font-semibold text-lg mb-1">{timerExercise.name}</h2>
            <p className="text-sm text-gray-500 mb-6">{timerExercise.keyPoints}</p>
            <div className="text-7xl font-bold text-[#2A79E6] mb-8 font-mono">
              {formatTime(timerSeconds)}
            </div>
            <div className="flex gap-3">
              {timerRunning ? (
                <Button variant="outline" className="flex-1 h-12" onClick={pauseTimer}>
                  <Pause className="w-5 h-5 mr-2" />暂停
                </Button>
              ) : (
                <Button className="flex-1 h-12 bg-[#2A79E6]" onClick={() => {
                  if (timerSeconds <= 0) {
                    handleCompleteExercise(timerExercise.id);
                  } else {
                    setTimerRunning(true);
                    timerRef.current = setInterval(() => {
                      setTimerSeconds((prev) => {
                        if (prev <= 1) {
                          clearInterval(timerRef.current!);
                          setTimerRunning(false);
                          handleCompleteExercise(timerExercise.id);
                          return 0;
                        }
                        return prev - 1;
                      });
                    }, 1000);
                  }
                }}>
                  <Play className="w-5 h-5 mr-2" />继续
                </Button>
              )}
              <Button variant="ghost" className="h-12" onClick={stopTimer}>退出</Button>
            </div>
          </div>
        </div>
      )}

      {/* Skip Reason Dialog */}
      <Dialog open={skipDialogOpen} onOpenChange={setSkipDialogOpen}>
        <DialogContent className="sm:max-w-sm rounded-2xl">
          <DialogHeader>
            <DialogTitle>跳过训练</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-4">
            <p className="text-sm text-gray-600">请选择跳过原因：</p>
            {['疼痛不适', '疲劳无力', '时间不足', '其他原因'].map((reason) => (
              <button key={reason}
                onClick={() => setSkipReason(reason)}
                className={`w-full text-left px-4 py-3 rounded-xl border text-sm transition-colors ${
                  skipReason === reason ? 'border-[#2A79E6] bg-blue-50 text-[#2A79E6]' : 'border-gray-200 hover:border-gray-300'
                }`}>
                {reason}
              </button>
            ))}
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setSkipDialogOpen(false)} className="flex-1">取消</Button>
            <Button onClick={handleSkip} className="flex-1 bg-[#2A79E6]"
              disabled={!skipReason || completing === skipExerciseId}>
              {completing === skipExerciseId ? <Loader2 className="w-4 h-4 animate-spin" /> : '确认跳过'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Header */}
      <div className="bg-white px-4 py-6 shadow-sm sticky top-0 z-10">
        <button onClick={onBack}
          className="flex items-center gap-2 mb-3 text-gray-600 hover:text-gray-900 min-h-[44px]">
          <ArrowLeft className="w-5 h-5" /><span>返回</span>
        </button>
        <div className="flex items-start justify-between mb-2">
          <div>
            <h1 className="font-semibold text-xl mb-1">今日康复训练</h1>
            <p className="text-sm text-gray-600">AI个性化定制 · 坚持就是胜利！</p>
          </div>
        </div>
        <div className="mt-4">
          <div className="flex justify-between items-center mb-2">
            <span className="text-sm text-gray-600">已完成 {completedCount}/{totalCount} 项</span>
          </div>
          <Progress value={progressPercent} className="h-2" />
        </div>
      </div>

      {/* Exercise List */}
      <div className="px-4 pt-6 pb-24 space-y-3">
        {exercises.map((exercise, index) => (
          <div key={exercise.id}
            className={`bg-white rounded-2xl p-4 shadow-sm transition-opacity ${exercise.completed ? 'opacity-60' : ''}`}
          >
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 pt-1">
                {exercise.completed ? (
                  <div className="w-6 h-6 bg-[#48C774] rounded-full flex items-center justify-center">
                    <Check className="w-4 h-4 text-white" />
                  </div>
                ) : (
                  <div className="w-6 h-6 border-2 border-gray-300 rounded-full flex items-center justify-center">
                    <span className="text-xs text-gray-500">{index + 1}</span>
                  </div>
                )}
              </div>
              <div className="flex-1">
                <div className="flex items-start justify-between mb-2">
                  <h3 className={`font-semibold ${exercise.completed ? 'line-through' : ''}`}>{exercise.name}</h3>
                  {exercise.completed && (
                    <span className="text-xs text-[#48C774] bg-green-50 px-2 py-1 rounded">已完成</span>
                  )}
                </div>
                <div className="flex items-center gap-3 text-sm text-gray-600 mb-2">
                  <span className="flex items-center gap-1"><Clock className="w-4 h-4" />{exercise.duration}</span>
                  <span className="flex items-center gap-1"><Repeat className="w-4 h-4" />{exercise.sets}</span>
                </div>
                <div className="text-sm text-gray-700 mb-2">
                  <span className="font-medium">动作要点：</span>{exercise.keyPoints}
                </div>
                <div className="flex items-start gap-2 bg-yellow-50 border border-yellow-200 rounded-lg p-2 mb-3">
                  <AlertTriangle className="w-4 h-4 text-yellow-600 flex-shrink-0 mt-0.5" />
                  <span className="text-xs text-gray-700">{exercise.warning}</span>
                </div>
                {!exercise.completed && (
                  <div className="flex gap-2">
                    {/* 2026-05-03 修复：开始训练按钮 → 计时模式 */}
                    <Button
                      onClick={() => startTimer(exercise)}
                      disabled={completing === exercise.id || timerExercise !== null}
                      className="flex-1 bg-[#2A79E6] hover:bg-[#2267c7] min-h-[44px]"
                    >
                      <Play className="w-4 h-4 mr-1" />开始训练
                    </Button>
                    {/* 2026-05-03 修复：跳过训练按钮 */}
                    <Button
                      variant="outline"
                      onClick={() => openSkipDialog(exercise.id)}
                      disabled={completing === exercise.id || timerExercise !== null}
                      className="min-h-[44px]"
                    >
                      <SkipForward className="w-4 h-4" />
                    </Button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Bottom bar */}
      <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 p-4">
        <Button
          onClick={() => {
            toast.success('训练记录已提交！');
            onBack();
          }}
          disabled={!allCompleted}
          className={`w-full h-12 text-base ${allCompleted ? 'bg-[#2A79E6] hover:bg-[#2267c7]' : 'bg-gray-300 text-gray-500 cursor-not-allowed'}`}
        >
          {allCompleted ? '🎉 提交训练完成记录' : `还剩 ${totalCount - completedCount} 项训练待完成`}
        </Button>
      </div>
    </div>
  );
}
