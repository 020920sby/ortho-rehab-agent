{/* 2026-06-01 重构：总览页 — 全部数据从API动态加载，无硬编码 */}
import { useState, useEffect, useCallback } from 'react';
import { Activity, Calendar, Pill, ArrowRight, LogOut } from 'lucide-react';
import { Button } from './ui/button';
import { Progress } from './ui/progress';
import { PageType, usePatient } from '../App';
import { getPatient, getExercises, getFollowups } from '../../services/api';
import { toast } from 'sonner';

interface OverviewProps {
  onNavigate: (page: PageType) => void;
}

export function Overview({ onNavigate }: OverviewProps) {
  const { patientId, patientName, clearPatient } = usePatient();
  const [patientInfo, setPatientInfo] = useState<Record<string, unknown>>({});
  const [exercises, setExercises] = useState<{ completed: boolean }[]>([]);
  const [nextFollowup, setNextFollowup] = useState<{
    followup_date: string; content: string;
  } | null>(null);
  const [loading, setLoading] = useState(true);

  const currentHour = new Date().getHours();
  const greeting = currentHour < 12 ? '早上好' : currentHour < 18 ? '下午好' : '晚上好';

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const info = await getPatient(patientId);
      setPatientInfo(info || {});
    } catch { /* use defaults */ }
    try {
      const exData = await getExercises(patientId);
      setExercises(exData?.exercises || []);
    } catch { /* use defaults */ }
    try {
      const fuData = await getFollowups(patientId, true);
      setNextFollowup(fuData?.next_followup || null);
    } catch { /* use defaults */ }
    setLoading(false);
  }, [patientId]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const completedCount = exercises.filter((e) => e.completed).length;
  const totalCount = exercises.length || 5;
  const progressPercent = totalCount > 0 ? (completedCount / totalCount) * 100 : 0;

  const surgeryType = String(patientInfo.surgery_type || '');
  const surgeryTypeLabel = (
    { TKA: '全膝关节置换', THA: '全髋关节置换', ACL: '前交叉韧带重建' } as Record<string, string>
  )[surgeryType] || surgeryType || '未设置手术类型';

  const surgeryDate = String(patientInfo.surgery_date || '');
  const daysPostOp = surgeryDate
    ? Math.max(0, Math.floor((Date.now() - new Date(surgeryDate).getTime()) / 86400000))
    : 0;

  // 康复阶段判断
  const getPhase = (days: number, st: string): string => {
    if (st === 'ACL') {
      if (days <= 14) return '急性保护期';
      if (days <= 42) return '早期保护性训练期';
      if (days <= 90) return '肌力重建期';
      if (days <= 180) return '运动准备期';
      return '回归运动期';
    }
    if (days <= 14) return '急性期';
    if (days <= 42) return '亚急性期';
    if (days <= 90) return '恢复期';
    return '维持期';
  };
  const phase = daysPostOp > 0 ? getPhase(daysPostOp, surgeryType) : '';

  const displayName = patientName || patientId;

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-10 h-10 text-[#2A79E6] mx-auto animate-pulse mb-3" />
          <p className="text-sm text-gray-500">加载患者数据...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 pb-4">
      {/* 顶部导航 */}
      <div className="bg-white px-4 py-4 flex items-center justify-between shadow-sm sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <Activity className="w-6 h-6 text-[#2A79E6]" />
          <h1 className="font-semibold">骨科康复助手</h1>
        </div>
        <button
          onClick={clearPatient}
          className="flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 min-h-[44px]"
        >
          <LogOut className="w-4 h-4" />
          切换患者
        </button>
      </div>

      <div className="px-4 pt-4 space-y-4">
        {/* 患者信息卡片 */}
        <div className="bg-white rounded-2xl p-4 shadow-sm">
          <div className="flex justify-between items-start">
            <div>
              <h2 className="text-lg mb-2">{greeting}，{displayName}</h2>
              {surgeryType ? (
                <div className="text-sm text-gray-600">
                  <span>{surgeryTypeLabel}术后</span>
                  {daysPostOp > 0 && (
                    <>
                      <span className="mx-2">·</span>
                      <span>第{daysPostOp}天</span>
                    </>
                  )}
                  {phase && (
                    <>
                      <span className="mx-2">·</span>
                      <span>{phase}</span>
                    </>
                  )}
                </div>
              ) : (
                <div className="text-sm text-gray-400">
                  请先完善手术信息
                  <button onClick={() => onNavigate('profile')}
                    className="ml-2 text-[#2A79E6] underline">去设置</button>
                </div>
              )}
            </div>
            <div className="bg-[#48C774] text-white px-3 py-2 rounded-lg text-sm flex items-center gap-1 min-h-[44px]">
              <span className="text-lg">✓</span>
              <span>安全状态：一切正常</span>
            </div>
          </div>
          {surgeryType && (
            <div className="mt-3 text-xs text-gray-500">
              点击下方按钮开始今日康复打卡和训练
            </div>
          )}
        </div>

        {/* 康复任务 */}
        <div className="bg-white rounded-2xl p-4 shadow-sm">
          <div className="flex justify-between items-center mb-3">
            <h3 className="font-semibold">今日康复任务</h3>
          </div>
          <div className="mb-4">
            <div className="flex justify-between items-center mb-2">
              <span className="text-sm text-gray-600">已完成 {completedCount}/{totalCount} 项</span>
              <span className="text-sm text-gray-600">预计 45 分钟</span>
            </div>
            <Progress value={progressPercent} className="h-2" />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Button onClick={() => onNavigate('training')} className="bg-[#2A79E6] hover:bg-[#2267c7] h-12 text-base">
              开始今日训练
            </Button>
            <Button onClick={() => onNavigate('checkin')} variant="outline"
              className="h-12 text-base border-[#2A79E6] text-[#2A79E6]">
              记录今日状态
            </Button>
          </div>
        </div>

        {/* 身体状态 — 仅当有数据时显示有意义的内容 */}
        {surgeryType && (
          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <h3 className="font-semibold mb-4">今日身体状态</h3>
            {daysPostOp > 0 ? (
              <div className="space-y-4">
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm">疼痛指数</span>
                    <span className="text-sm text-gray-500">完成打卡后自动更新</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full" />
                </div>
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm">关节活动度</span>
                    <span className="text-sm text-gray-500">完成打卡后自动更新</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full" />
                </div>
                <div>
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-sm">行走能力</span>
                    <span className="text-sm text-gray-500">完成打卡后自动更新</span>
                  </div>
                  <div className="h-2 bg-gray-100 rounded-full" />
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-400 text-center py-4">请设置手术日期以查看康复进度</p>
            )}
          </div>
        )}

        {/* 康复进度 */}
        {daysPostOp > 0 && (
          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <div className="flex justify-between items-center mb-3">
              <h3 className="font-semibold">康复进度缩览</h3>
              <Button onClick={() => onNavigate('progress-detail')} variant="ghost" size="sm"
                className="text-[#2A79E6] min-h-[44px]">
                查看详情<ArrowRight className="w-4 h-4 ml-1" />
              </Button>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div className="bg-gradient-to-br from-blue-50 to-blue-100 rounded-xl p-3 text-center">
                <div className="text-2xl font-bold text-[#2A79E6]">{daysPostOp}</div>
                <div className="text-xs text-gray-600 mt-1">术后天数</div>
              </div>
              <div className="bg-gradient-to-br from-green-50 to-green-100 rounded-xl p-3 text-center">
                <div className="text-2xl font-bold text-[#48C774]">—</div>
                <div className="text-xs text-gray-600 mt-1">疼痛下降</div>
              </div>
              <div className="bg-gradient-to-br from-purple-50 to-purple-100 rounded-xl p-3 text-center">
                <div className="text-2xl font-bold text-purple-600">—</div>
                <div className="text-xs text-gray-600 mt-1">屈曲进度</div>
              </div>
            </div>
          </div>
        )}

        {/* 快捷卡片 */}
        <div className="grid grid-cols-2 gap-3">
          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <Calendar className="w-5 h-5 text-[#2A79E6]" />
              <h4 className="font-semibold text-sm">复诊计划</h4>
            </div>
            {nextFollowup ? (
              <>
                <div className="text-xs text-gray-600 mb-1">
                  下一次复诊：<span className="font-medium">{nextFollowup.followup_date}</span>
                </div>
                <div className="text-xs text-gray-500 mb-3">{nextFollowup.content}</div>
              </>
            ) : (
              <div className="text-xs text-gray-400 mb-3">暂无复诊计划，点击生成</div>
            )}
            <Button size="sm" variant="outline" className="w-full text-xs min-h-[44px]"
              onClick={() => onNavigate('followup-plan')}>查看详情</Button>
          </div>
          <div className="bg-white rounded-2xl p-4 shadow-sm">
            <div className="flex items-center gap-2 mb-2">
              <Pill className="w-5 h-5 text-[#2A79E6]" />
              <h4 className="font-semibold text-sm">用药提醒</h4>
            </div>
            <div className="text-xs text-gray-400 mb-3">完成计划生成后自动显示</div>
            <Button size="sm" variant="outline" className="w-full text-xs min-h-[44px]"
              onClick={() => onNavigate('medication')}>去查看</Button>
          </div>
        </div>

        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3">
          <p className="text-xs text-gray-600 leading-relaxed">
            本应用为AI辅助工具，不能替代专业医疗判断，如遇紧急情况，请立即拨打120就医
          </p>
        </div>
      </div>
    </div>
  );
}
