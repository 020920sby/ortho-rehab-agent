{/* 2026-06-01: 欢迎引导页 — 新用户首次打开的空状态 */}
import { useState } from 'react';
import { Activity, Upload, Users, UserPlus, ChevronRight, FileText, Loader2, Stethoscope } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { toast } from 'sonner';
import { usePatient } from '../App';
import { uploadOrder, listPatients, PatientListItem } from '../../services/api';
import { OrderUpload } from './OrderUpload';

interface WelcomePageProps {
  onPatientSelected: (patientId: string, patientName: string) => void;
}

export function WelcomePage({ onPatientSelected }: WelcomePageProps) {
  const { patientId, setPatientId, refreshPatient } = usePatient();
  const [showPatientSelector, setShowPatientSelector] = useState(false);
  const [showQuickCreate, setShowQuickCreate] = useState(false);
  const [showOrderUpload, setShowOrderUpload] = useState(false);

  return (
    <div className="min-h-screen bg-gradient-to-b from-blue-50 to-white flex flex-col">
      {/* Hero 区域 */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 pt-12 pb-8">
        <div className="w-20 h-20 bg-gradient-to-br from-[#2A79E6] to-[#4A90FF] rounded-2xl flex items-center justify-center mb-6 shadow-lg shadow-blue-200">
          <Activity className="w-10 h-10 text-white" />
        </div>
        <h1 className="text-2xl font-bold text-gray-900 mb-2">骨科康复助手</h1>
        <p className="text-sm text-gray-500 text-center mb-8">
          AI 驱动的个性化术后康复管理
        </p>

        {/* 主操作按钮 */}
        <div className="w-full max-w-sm space-y-3">
          <Button
            onClick={() => setShowOrderUpload(true)}
            className="w-full h-14 text-base bg-[#2A79E6] hover:bg-[#2267c7] shadow-lg shadow-blue-200 rounded-xl"
          >
            <Upload className="w-5 h-5 mr-2" />
            上传病历创建档案
          </Button>
          <p className="text-xs text-gray-400 text-center">上传出院小结或手术记录，AI 自动解析并创建康复档案</p>

          <div className="relative my-4">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-gray-200"></div></div>
            <div className="relative flex justify-center text-xs"><span className="bg-gradient-to-b from-blue-50 to-white px-2 text-gray-400">或</span></div>
          </div>

          <Button
            onClick={() => setShowPatientSelector(true)}
            variant="outline"
            className="w-full h-14 text-base border-2 border-gray-300 hover:border-[#2A79E6] hover:text-[#2A79E6] rounded-xl"
          >
            <Users className="w-5 h-5 mr-2" />
            选择已有患者
          </Button>

          <Button
            onClick={() => setShowQuickCreate(true)}
            variant="ghost"
            className="w-full h-12 text-sm text-gray-500 hover:text-[#2A79E6]"
          >
            <UserPlus className="w-4 h-4 mr-2" />
            快速创建新患者
          </Button>
        </div>
      </div>

      {/* 底部免责 */}
      <div className="px-6 pb-8">
        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-3 max-w-sm mx-auto">
          <p className="text-xs text-gray-600 leading-relaxed text-center">
            本应用为AI辅助工具，不能替代专业医疗判断，如遇紧急情况，请立即拨打120就医
          </p>
        </div>
      </div>

      {/* ── 弹窗 1: 患者选择器 ────────────────────── */}
      <PatientSelectorDialog
        open={showPatientSelector}
        onOpenChange={setShowPatientSelector}
        onSelect={(id, name) => {
          onPatientSelected(id, name);
          setShowPatientSelector(false);
        }}
      />

      {/* ── 弹窗 2: 快速创建 ──────────────────────── */}
      <QuickCreateDialog
        open={showQuickCreate}
        onOpenChange={setShowQuickCreate}
        onCreated={(id, name) => {
          onPatientSelected(id, name);
          setShowQuickCreate(false);
        }}
      />

      {/* ── 弹窗 3: 上传病历创建 ──────────────────── */}
      <OrderUploadDialog
        open={showOrderUpload}
        onOpenChange={setShowOrderUpload}
        onPatientCreated={(id, name) => {
          onPatientSelected(id, name);
          setShowOrderUpload(false);
        }}
      />
    </div>
  );
}


// ═══════════════════════════════════════════════════════════
// 子组件：患者选择器弹窗
// ═══════════════════════════════════════════════════════════

function PatientSelectorDialog({
  open, onOpenChange, onSelect,
}: {
  open: boolean; onOpenChange: (v: boolean) => void;
  onSelect: (patientId: string, patientName: string) => void;
}) {
  const [patients, setPatients] = useState<PatientListItem[]>([]);
  const [loading, setLoading] = useState(false);

  const loadPatients = async () => {
    setLoading(true);
    try {
      const list = await listPatients();
      setPatients(list);
    } catch {
      toast.error('加载患者列表失败');
    } finally {
      setLoading(false);
    }
  };

  // 每次打开弹窗时刷新列表
  const handleOpen = (v: boolean) => {
    onOpenChange(v);
    if (v) loadPatients();
  };

  const presetPatients = [
    { id: '001', label: '预设患者 001', description: '测试用' },
    { id: '002', label: '预设患者 002', description: '测试用' },
    { id: '003', label: '预设患者 003', description: '测试用' },
  ];

  const surgeryLabels: Record<string, string> = {
    TKA: '膝关节置换', THA: '髋关节置换', ACL: '前交叉韧带重建',
  };

  return (
    <Dialog open={open} onOpenChange={handleOpen}>
      <DialogContent className="max-w-md max-h-[70vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Users className="w-5 h-5 text-[#2A79E6]" />选择患者
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* 预设快捷选项 */}
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">快捷测试</p>
            <div className="space-y-2">
              {presetPatients.map((p) => (
                <button
                  key={p.id}
                  onClick={() => onSelect(p.id, p.label)}
                  className="w-full flex items-center gap-3 p-3 rounded-xl border border-gray-200 hover:border-[#2A79E6] hover:bg-blue-50 transition-colors"
                >
                  <div className="w-10 h-10 bg-gray-100 rounded-full flex items-center justify-center">
                    <Users className="w-5 h-5 text-gray-500" />
                  </div>
                  <div className="flex-1 text-left">
                    <div className="font-medium text-sm">{p.label}</div>
                    <div className="text-xs text-gray-400">{p.description}</div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-gray-300" />
                </button>
              ))}
            </div>
          </div>

          {/* 数据库已有患者 */}
          <div>
            <p className="text-xs font-medium text-gray-500 mb-2">
              已有档案 {loading && <Loader2 className="w-3 h-3 inline animate-spin" />}
            </p>
            {patients.length === 0 && !loading ? (
              <p className="text-sm text-gray-400 text-center py-4">暂无患者档案，请先上传病历创建</p>
            ) : (
              <div className="space-y-2">
                {patients.map((p) => (
                  <button
                    key={p.patient_id}
                    onClick={() => onSelect(p.patient_id, p.name || p.patient_id)}
                    className="w-full flex items-center gap-3 p-3 rounded-xl border border-gray-200 hover:border-[#2A79E6] hover:bg-blue-50 transition-colors"
                  >
                    <div className="w-10 h-10 bg-blue-100 rounded-full flex items-center justify-center">
                      <Stethoscope className="w-5 h-5 text-[#2A79E6]" />
                    </div>
                    <div className="flex-1 text-left">
                      <div className="font-medium text-sm">
                        {p.name || `患者 ${p.patient_id}`}
                      </div>
                      <div className="text-xs text-gray-400">
                        {p.surgery_type ? surgeryLabels[p.surgery_type] || p.surgery_type : '未设置手术类型'}
                        {p.days_post_op > 0 ? ` · 术后第${p.days_post_op}天` : ''}
                      </div>
                    </div>
                    <ChevronRight className="w-4 h-4 text-gray-300" />
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}


// ═══════════════════════════════════════════════════════════
// 子组件：快速创建患者
// ═══════════════════════════════════════════════════════════

function QuickCreateDialog({
  open, onOpenChange, onCreated,
}: {
  open: boolean; onOpenChange: (v: boolean) => void;
  onCreated: (patientId: string, patientName: string) => void;
}) {
  const [patientId, setPatientId] = useState('');
  const [surgeryType, setSurgeryType] = useState('');
  const [surgeryDate, setSurgeryDate] = useState('');
  const [creating, setCreating] = useState(false);

  const handleCreate = async () => {
    if (!patientId.trim()) { toast.error('请输入患者ID'); return; }
    setCreating(true);
    try {
      const { updatePatient } = await import('../../services/api');
      await updatePatient(patientId.trim(), {
        surgery_type: surgeryType || undefined,
        surgery_date: surgeryDate || undefined,
      });
      toast.success('患者档案已创建');
      onCreated(patientId.trim(), patientId.trim());
    } catch {
      toast.error('创建失败');
    } finally {
      setCreating(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserPlus className="w-5 h-5 text-[#2A79E6]" />快速创建患者
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-4 pt-2">
          <div>
            <label className="text-sm font-medium mb-1 block">患者 ID *</label>
            <Input
              value={patientId}
              onChange={(e) => setPatientId(e.target.value)}
              placeholder="例如：P001"
              className="min-h-[44px]"
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">手术类型</label>
            <Select value={surgeryType} onValueChange={setSurgeryType}>
              <SelectTrigger className="min-h-[44px]">
                <SelectValue placeholder="选择手术类型（可跳过）" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="TKA">TKA（全膝关节置换）</SelectItem>
                <SelectItem value="THA">THA（全髋关节置换）</SelectItem>
                <SelectItem value="ACL">ACL（前交叉韧带重建）</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">手术日期</label>
            <Input
              type="date"
              value={surgeryDate}
              onChange={(e) => setSurgeryDate(e.target.value)}
              className="min-h-[44px]"
            />
          </div>
          <Button
            onClick={handleCreate}
            disabled={!patientId.trim() || creating}
            className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12"
          >
            {creating ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
            创建并进入
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}


// ═══════════════════════════════════════════════════════════
// 子组件：上传病历 → 解析 → 创建患者
// ═══════════════════════════════════════════════════════════

function OrderUploadDialog({
  open, onOpenChange, onPatientCreated,
}: {
  open: boolean; onOpenChange: (v: boolean) => void;
  onPatientCreated: (patientId: string, patientName: string) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [parsed, setParsed] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState('');
  const [confirming, setConfirming] = useState(false);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      const ext = f.name.split('.').pop()?.toLowerCase();
      const allowed = ['pdf', 'docx', 'txt', 'md', 'jpg', 'jpeg', 'png'];
      if (!allowed.includes(ext || '')) {
        toast.error(`不支持 .${ext}，支持：${allowed.join(', ')}`);
        return;
      }
      setFile(f);
      setParsed(null);
      setError('');
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError('');
    try {
      const { uploadOrder } = await import('../../services/api');
      const result = await uploadOrder(file);
      if (result.error) {
        setError(result.error);
      } else {
        setParsed(result.parsed || {});
      }
    } catch {
      setError('上传失败，请检查网络');
    } finally {
      setUploading(false);
    }
  };

  const handleConfirmAndCreate = async () => {
    if (!parsed) return;
    setConfirming(true);
    try {
      const patientId = (parsed.patient_name as string)?.replace(/\s/g, '_') ||
                        `P${Date.now().toString(36).toUpperCase()}`;
      const { updatePatient } = await import('../../services/api');
      await updatePatient(patientId, {
        name: parsed.patient_name || '',
        surgery_type: parsed.surgery_type || '',
        surgery_date: parsed.surgery_date || '',
      });
      toast.success(`患者档案已创建：${parsed.patient_name || patientId}`);
      onPatientCreated(patientId, (parsed.patient_name as string) || patientId);
    } catch {
      toast.error('创建患者失败');
    } finally {
      setConfirming(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setParsed(null);
    setError('');
  };

  const surgeryLabels: Record<string, string> = {
    TKA: '全膝关节置换', THA: '全髋关节置换', ACL: '前交叉韧带重建',
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) handleReset(); }}>
      <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#2A79E6]" />上传病历创建档案
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* 文件选择 */}
          {!parsed && (
            <>
              <div
                className="border-2 border-dashed border-gray-300 rounded-xl p-8 text-center cursor-pointer hover:border-[#2A79E6] transition-colors"
                onClick={() => document.getElementById('welcome-ocr-input')?.click()}
              >
                <input
                  id="welcome-ocr-input"
                  type="file"
                  accept=".pdf,.docx,.txt,.md,.jpg,.jpeg,.png"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                {file ? (
                  <div className="space-y-2">
                    <FileText className="w-10 h-10 text-[#2A79E6] mx-auto" />
                    <p className="text-sm font-medium">{file.name}</p>
                    <p className="text-xs text-gray-400">{(file.size / 1024).toFixed(0)} KB</p>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <Upload className="w-10 h-10 text-gray-400 mx-auto" />
                    <p className="text-sm text-gray-600">点击选择出院小结或手术记录</p>
                    <p className="text-xs text-gray-400">支持 PDF、Word、图片</p>
                  </div>
                )}
              </div>

              <Button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12"
              >
                {uploading ? <><Loader2 className="w-4 h-4 animate-spin mr-2" />AI 解析中...</> : '开始解析'}
              </Button>

              {error && (
                <div className="bg-red-50 rounded-xl p-4 text-sm text-red-700">{error}</div>
              )}
            </>
          )}

          {/* 解析结果确认 */}
          {parsed && (
            <div className="space-y-4">
              <div className="bg-green-50 rounded-xl p-4 space-y-3">
                <p className="text-sm font-medium text-green-700">✅ AI 解析完成，请确认以下信息：</p>
                <div className="grid grid-cols-2 gap-2 text-sm">
                  {parsed.patient_name && (
                    <div className="bg-white rounded-lg p-3">
                      <div className="text-xs text-gray-400">患者姓名</div>
                      <div className="font-medium">{String(parsed.patient_name)}</div>
                    </div>
                  )}
                  {parsed.surgery_type && (
                    <div className="bg-white rounded-lg p-3">
                      <div className="text-xs text-gray-400">手术类型</div>
                      <div className="font-medium">{surgeryLabels[String(parsed.surgery_type)] || String(parsed.surgery_type)}</div>
                    </div>
                  )}
                  {parsed.surgery_date && (
                    <div className="bg-white rounded-lg p-3">
                      <div className="text-xs text-gray-400">手术日期</div>
                      <div className="font-medium">{String(parsed.surgery_date)}</div>
                    </div>
                  )}
                  {parsed.diagnosis && (
                    <div className="bg-white rounded-lg p-3 col-span-2">
                      <div className="text-xs text-gray-400">诊断</div>
                      <div className="font-medium text-sm">{String(parsed.diagnosis)}</div>
                    </div>
                  )}
                </div>
              </div>

              <Button
                onClick={handleConfirmAndCreate}
                disabled={confirming}
                className="w-full bg-[#48C774] hover:bg-[#3ab564] h-12 text-base"
              >
                {confirming ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : null}
                确认并创建康复档案
              </Button>

              <Button variant="ghost" onClick={handleReset} className="w-full text-sm">
                重新上传
              </Button>
            </div>
          )}

          <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-500 space-y-1">
            <p>📋 上传出院小结或手术记录可获得最佳效果</p>
            <p>🔒 病历数据仅存储在本地</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
