{/* 2026-06-01: OCR医嘱上传组件 — Profile页病历医嘱管理入口 */}
import { useState, useRef } from 'react';
import { Upload, FileText, Loader2, CheckCircle, AlertCircle } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from './ui/dialog';
import { uploadOrder } from '../../services/api';
import { toast } from 'sonner';

interface ParsedOrder {
  patient_name?: string;
  surgery_type?: string;
  surgery_date?: string;
  diagnosis?: string;
  surgical_procedure?: string;
  medications?: Array<{
    drug_name: string;
    dosage: string;
    frequency: string;
    duration: string;
    notes: string;
  }>;
  rehabilitation_plan?: string;
  precautions?: string[];
  weight_bearing?: string;
  rom_target?: string;
  follow_up?: string;
}

interface UploadResult {
  filename: string;
  raw_text_preview: string;
  parsed: ParsedOrder;
  error: string;
}

export function OrderUpload() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<UploadResult | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) {
      const ext = f.name.split('.').pop()?.toLowerCase();
      const allowed = ['pdf', 'docx', 'txt', 'md', 'jpg', 'jpeg', 'png'];
      if (!allowed.includes(ext || '')) {
        toast.error(`不支持的文件类型 .${ext}，支持：${allowed.join(', ')}`);
        return;
      }
      if (f.size > 20 * 1024 * 1024) {
        toast.error('文件大小不能超过 20MB');
        return;
      }
      setFile(f);
      setResult(null);
    }
  };

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    try {
      const data = await uploadOrder(file);
      setResult(data);
      if (data.error) {
        toast.error(data.error);
      } else if (data.parsed?.surgery_type) {
        toast.success(`解析成功：${data.parsed.surgery_type}手术医嘱已识别`);
      } else {
        toast.success('文件已上传解析，请查看结果');
      }
    } catch {
      toast.error('上传失败，请检查网络连接后重试');
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setResult(null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const formatLabel = (key: string): string => {
    const labels: Record<string, string> = {
      patient_name: '患者姓名',
      surgery_type: '手术类型',
      surgery_date: '手术日期',
      diagnosis: '术前诊断',
      surgical_procedure: '手术名称',
      rehabilitation_plan: '康复指导',
      weight_bearing: '负重限制',
      rom_target: '活动度目标',
      follow_up: '随访安排',
    };
    return labels[key] || key;
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <button className="w-full flex items-center gap-4 px-5 py-4 hover:bg-gray-50 transition-colors min-h-[60px]">
          <div className="flex-shrink-0 w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center">
            <Upload className="w-5 h-5 text-[#2A79E6]" />
          </div>
          <div className="flex-1 text-left">
            <div className="font-medium text-sm mb-1">上传医嘱</div>
            <div className="text-xs text-gray-500">拍照或上传PDF/DOCX自动解析</div>
          </div>
        </button>
      </DialogTrigger>

      <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-[#2A79E6]" />
            上传医嘱文档
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* 文件选择区 */}
          <div
            className="border-2 border-dashed border-gray-300 rounded-xl p-6 text-center cursor-pointer hover:border-[#2A79E6] transition-colors"
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt,.md,.jpg,.jpeg,.png"
              onChange={handleFileChange}
              className="hidden"
            />
            {file ? (
              <div className="space-y-2">
                <FileText className="w-10 h-10 text-[#2A79E6] mx-auto" />
                <p className="text-sm font-medium text-gray-700">{file.name}</p>
                <p className="text-xs text-gray-500">{(file.size / 1024).toFixed(0)} KB</p>
              </div>
            ) : (
              <div className="space-y-2">
                <Upload className="w-10 h-10 text-gray-400 mx-auto" />
                <p className="text-sm text-gray-600">点击选择文件</p>
                <p className="text-xs text-gray-400">支持 PDF、Word、图片、文本</p>
              </div>
            )}
          </div>

          {/* 操作按钮 */}
          <div className="flex gap-2">
            <Button
              onClick={handleUpload}
              disabled={!file || uploading}
              className="flex-1 bg-[#2A79E6] hover:bg-[#2267c7]"
            >
              {uploading ? (
                <><Loader2 className="w-4 h-4 animate-spin mr-2" />解析中...</>
              ) : (
                '开始解析'
              )}
            </Button>
            {file && (
              <Button variant="outline" onClick={handleReset} disabled={uploading}>
                重置
              </Button>
            )}
          </div>

          {/* 解析结果 */}
          {result && !result.error && (
            <div className="bg-green-50 rounded-xl p-4 space-y-3">
              <div className="flex items-center gap-2 text-green-700">
                <CheckCircle className="w-4 h-4" />
                <span className="text-sm font-medium">解析成功</span>
              </div>

              {/* 基本信息 */}
              <div className="grid grid-cols-2 gap-2 text-sm">
                {Object.entries(result.parsed || {}).filter(([k, v]) =>
                  ['patient_name', 'surgery_type', 'surgery_date', 'diagnosis'].includes(k) && v
                ).map(([k, v]) => (
                  <div key={k} className="bg-white rounded-lg p-2">
                    <div className="text-xs text-gray-500">{formatLabel(k)}</div>
                    <div className="font-medium text-gray-800">{String(v)}</div>
                  </div>
                ))}
              </div>

              {/* 用药列表 */}
              {result.parsed?.medications && result.parsed.medications.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-600 mb-2">用药信息</div>
                  <div className="space-y-1">
                    {result.parsed.medications.map((med, i) => (
                      <div key={i} className="bg-white rounded-lg p-2 text-sm">
                        <span className="font-medium">{med.drug_name}</span>
                        {med.dosage && <span className="text-gray-500"> · {med.dosage}</span>}
                        {med.frequency && <span className="text-gray-500"> · {med.frequency}</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 康复指导 */}
              {result.parsed?.precautions && result.parsed.precautions.length > 0 && (
                <div>
                  <div className="text-xs font-medium text-gray-600 mb-2">注意事项</div>
                  <div className="space-y-1">
                    {result.parsed.precautions.map((p, i) => (
                      <div key={i} className="bg-white rounded-lg p-2 text-sm text-gray-700">
                        ⚠ {p}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 文本预览 */}
              {result.raw_text_preview && (
                <details className="text-xs">
                  <summary className="text-gray-500 cursor-pointer">查看原文预览</summary>
                  <pre className="mt-2 bg-white rounded-lg p-3 whitespace-pre-wrap text-gray-600 max-h-32 overflow-y-auto">
                    {result.raw_text_preview}
                  </pre>
                </details>
              )}
            </div>
          )}

          {/* 错误提示 */}
          {result?.error && (
            <div className="bg-red-50 rounded-xl p-4 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
              <div className="text-sm text-red-700">{result.error}</div>
            </div>
          )}

          {/* 使用说明 */}
          <div className="bg-gray-50 rounded-lg p-3 text-xs text-gray-500 space-y-1">
            <p>📋 <strong>支持格式：</strong>PDF、Word(.docx)、文本(.txt/.md)、图片(.jpg/.png)</p>
            <p>🔍 系统将自动识别手术类型、日期、用药方案和康复指导</p>
            <p>💡 上传出院小结或手术记录可获得最佳解析效果</p>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
