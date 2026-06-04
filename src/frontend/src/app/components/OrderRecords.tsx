{/* 2026-06-01: 医嘱记录查看 — 历史上传列表 + 解析详情 */}
import { useState, useEffect, useCallback } from 'react';
import { FileText, ChevronLeft, ChevronRight, Calendar, Loader2, Stethoscope, User, AlertCircle } from 'lucide-react';
import { Button } from './ui/button';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from './ui/dialog';
import { toast } from 'sonner';
import { usePatient } from '../App';
import { getOrderRecords, getOrderDetail, OrderRecord, OrderDetail } from '../../services/api';

interface OrderRecordsProps {
  onBack: () => void;
}

const SURGERY_LABELS: Record<string, string> = {
  TKA: '全膝关节置换', THA: '全髋关节置换', ACL: '前交叉韧带重建',
};

export function OrderRecordsPage({ onBack }: OrderRecordsProps) {
  const { patientId } = usePatient();
  const [orders, setOrders] = useState<OrderRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedOrder, setSelectedOrder] = useState<OrderDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [showDetail, setShowDetail] = useState(false);

  const fetchOrders = useCallback(async () => {
    setLoading(true);
    try {
      const data = await getOrderRecords(patientId);
      setOrders(data || []);
    } catch {
      toast.error('加载医嘱记录失败');
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    fetchOrders();
  }, [fetchOrders]);

  const handleViewDetail = async (orderId: number) => {
    setDetailLoading(true);
    setShowDetail(true);
    try {
      const detail = await getOrderDetail(patientId, orderId);
      setSelectedOrder(detail);
    } catch {
      toast.error('加载详情失败');
    } finally {
      setDetailLoading(false);
    }
  };

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
      <div className="bg-white px-4 py-4 flex items-center gap-3 shadow-sm sticky top-0 z-10">
        <button onClick={onBack} className="min-h-[44px] min-w-[44px] flex items-center justify-center">
          <ChevronLeft className="w-6 h-6 text-gray-600" />
        </button>
        <div>
          <h1 className="font-semibold text-lg">医嘱记录</h1>
          <p className="text-xs text-gray-500">{orders.length} 条记录</p>
        </div>
      </div>

      <div className="px-4 pt-4">
        {orders.length === 0 ? (
          <div className="bg-white rounded-2xl p-8 text-center shadow-sm">
            <FileText className="w-12 h-12 text-gray-300 mx-auto mb-4" />
            <p className="text-gray-500 mb-2">暂无医嘱记录</p>
            <p className="text-sm text-gray-400">上传出院小结或手术记录后，解析结果将自动保存在此</p>
          </div>
        ) : (
          <div className="space-y-3">
            {orders.map((order) => (
              <button key={order.id}
                onClick={() => handleViewDetail(order.id)}
                className="w-full bg-white rounded-2xl p-4 shadow-sm flex items-center gap-3 hover:bg-gray-50 transition-colors text-left">
                <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center flex-shrink-0">
                  <FileText className="w-5 h-5 text-[#2A79E6]" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="font-medium text-sm truncate">{order.filename}</div>
                  <div className="text-xs text-gray-400 mt-0.5">
                    {order.created_at?.slice(0, 10)} · {order.source_type === 'ocr' ? 'OCR识别' : '上传'}
                  </div>
                </div>
                <ChevronRight className="w-5 h-5 text-gray-400 flex-shrink-0" />
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Detail Dialog */}
      <Dialog open={showDetail} onOpenChange={setShowDetail}>
        <DialogContent className="max-w-md max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="w-5 h-5 text-[#2A79E6]" />医嘱详情
            </DialogTitle>
          </DialogHeader>

          {detailLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="w-6 h-6 text-[#2A79E6] animate-spin" />
            </div>
          ) : selectedOrder ? (
            <div className="space-y-4 pt-2">
              <div className="text-sm text-gray-500">
                <span className="font-medium">文件名：</span>{selectedOrder.filename}
              </div>
              <div className="text-sm text-gray-500">
                <span className="font-medium">上传时间：</span>{selectedOrder.created_at}
              </div>

              {/* Parsed data */}
              {selectedOrder.parsed_data && Object.keys(selectedOrder.parsed_data).length > 0 && (
                <div className="bg-green-50 rounded-xl p-4 space-y-3">
                  <p className="text-sm font-medium text-green-700">📋 AI 解析结果</p>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    {selectedOrder.parsed_data.patient_name && (
                      <div className="bg-white rounded-lg p-3 col-span-2">
                        <div className="text-xs text-gray-400">患者姓名</div>
                        <div className="font-medium">{String(selectedOrder.parsed_data.patient_name)}</div>
                      </div>
                    )}
                    {selectedOrder.parsed_data.surgery_type && (
                      <div className="bg-white rounded-lg p-3">
                        <div className="text-xs text-gray-400">手术类型</div>
                        <div className="font-medium">
                          {SURGERY_LABELS[String(selectedOrder.parsed_data.surgery_type)] || String(selectedOrder.parsed_data.surgery_type)}
                        </div>
                      </div>
                    )}
                    {selectedOrder.parsed_data.surgery_date && (
                      <div className="bg-white rounded-lg p-3">
                        <div className="text-xs text-gray-400">手术日期</div>
                        <div className="font-medium">{String(selectedOrder.parsed_data.surgery_date)}</div>
                      </div>
                    )}
                    {selectedOrder.parsed_data.diagnosis && (
                      <div className="bg-white rounded-lg p-3 col-span-2">
                        <div className="text-xs text-gray-400">诊断</div>
                        <div className="font-medium text-sm">{String(selectedOrder.parsed_data.diagnosis)}</div>
                      </div>
                    )}
                    {selectedOrder.parsed_data.doctor_name && (
                      <div className="bg-white rounded-lg p-3">
                        <div className="text-xs text-gray-400">主治医生</div>
                        <div className="font-medium">{String(selectedOrder.parsed_data.doctor_name)}</div>
                      </div>
                    )}
                    {selectedOrder.parsed_data.medications && (
                      <div className="bg-white rounded-lg p-3 col-span-2">
                        <div className="text-xs text-gray-400">用药</div>
                        <div className="font-medium text-sm">{String(selectedOrder.parsed_data.medications)}</div>
                      </div>
                    )}
                    {selectedOrder.parsed_data.precautions && (
                      <div className="bg-white rounded-lg p-3 col-span-2">
                        <div className="text-xs text-gray-400">注意事项</div>
                        <div className="font-medium text-sm">{String(selectedOrder.parsed_data.precautions)}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* Raw text preview */}
              {selectedOrder.raw_text_preview && (
                <div className="bg-gray-50 rounded-xl p-4">
                  <p className="text-xs font-medium text-gray-500 mb-2">原文预览</p>
                  <p className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed">
                    {selectedOrder.raw_text_preview.slice(0, 500)}
                    {selectedOrder.raw_text_preview.length > 500 && '...'}
                  </p>
                </div>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>
    </div>
  );
}
