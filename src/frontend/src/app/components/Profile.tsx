{/* 2026-06-01 修复：个人信息管理页面 - 添加OCR医嘱上传入口 */}
import { useState, useEffect, useCallback } from 'react';
import { Avatar, AvatarFallback } from './ui/avatar';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from './ui/select';
import { FileText, Pill, Calendar, Bell, Lock, Info, ChevronRight, User as UserIcon, Stethoscope, ClipboardList, Phone, Loader2, Edit3, Save, X, Upload } from 'lucide-react';
import { toast } from 'sonner';
import { PageType, usePatient } from '../App';
import { getPatient, updatePatient } from '../../services/api';
import { OrderUpload } from './OrderUpload';
import { EmergencyContactDialog } from './EmergencyContactDialog';

interface ProfileProps {
  onNavigate: (page: PageType) => void;
}

export function Profile({ onNavigate }: ProfileProps) {
  const { patientId, patientName, refreshPatient } = usePatient();
  const [patientInfo, setPatientInfo] = useState<Record<string, unknown>>({});
  const [loading, setLoading] = useState(true);
  const [editMode, setEditMode] = useState(false);
  const [saving, setSaving] = useState(false);

  // 编辑表单状态
  const [editName, setEditName] = useState('');
  const [editAge, setEditAge] = useState('');
  const [editGender, setEditGender] = useState('');
  const [editSurgeryType, setEditSurgeryType] = useState('');
  const [editSurgeryDate, setEditSurgeryDate] = useState('');
  const [editDoctorName, setEditDoctorName] = useState('');
  const [editContact, setEditContact] = useState('');
  const [showEmergencyContacts, setShowEmergencyContacts] = useState(false);

  const fetchProfile = useCallback(async () => {
    try {
      setLoading(true);
      const info = await getPatient(patientId);
      setPatientInfo(info || {});
    } catch {
      /* use defaults */
    } finally {
      setLoading(false);
    }
  }, [patientId]);

  useEffect(() => {
    fetchProfile();
  }, [fetchProfile]);

  const enterEditMode = () => {
    setEditName(String(patientInfo.name || patientName));
    setEditAge(patientInfo.age ? String(patientInfo.age) : '');
    setEditGender(String(patientInfo.gender || ''));
    setEditSurgeryType(String(patientInfo.surgery_type || ''));
    setEditSurgeryDate(String(patientInfo.surgery_date || ''));
    setEditDoctorName(String(patientInfo.doctor_name || ''));
    setEditContact(String(patientInfo.contact || ''));
    setEditMode(true);
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const updates: Record<string, unknown> = {
        name: editName,
        age: editAge ? parseInt(editAge, 10) : null,
        gender: editGender,
        surgery_type: editSurgeryType,
        surgery_date: editSurgeryDate,
        doctor_name: editDoctorName,
        contact: editContact,
      };
      await updatePatient(patientId, updates);
      toast.success('个人信息已保存');
      setEditMode(false);
      refreshPatient();
      fetchProfile();
    } catch {
      toast.error('保存失败，请稍后重试');
    } finally {
      setSaving(false);
    }
  };

  const surgeryType = String(patientInfo.surgery_type || 'TKA');
  const surgeryDate = String(patientInfo.surgery_date || '');
  const recoveryPhase = String(patientInfo.recovery_phase || '亚急性期');

  const menuItems = [
    {
      section: '康复计划配置',
      items: [
        { title: '用药计划', subtitle: '管理用药提醒和服药记录', icon: Pill, action: () => onNavigate('medication') },
        { title: '复诊计划', subtitle: '管理复诊安排和提醒', icon: Calendar, action: () => onNavigate('followup-plan') },
        { title: '紧急联系人', subtitle: '设置家属/医生联系方式', icon: Phone, action: () => setShowEmergencyContacts(true) },
      ],
    },
    {
      section: '病历医嘱管理',
      items: [
        { title: '出院小结', subtitle: '已上传 1 份', icon: FileText, action: undefined, isUpload: true },
        { title: '医嘱记录', subtitle: '查看所有医嘱与康复指导', icon: ClipboardList, action: () => onNavigate('order-records') },
      ],
    },
    {
      section: '系统设置',
      items: [
        { title: '通知设置', subtitle: '管理推送通知和提醒', icon: Bell, action: () => onNavigate('notification-settings') },
        { title: '隐私与安全', subtitle: '数据隐私、账号安全', icon: Lock, action: () => onNavigate('privacy-security') },
        { title: '关于与帮助', subtitle: '产品介绍、使用帮助、联系客服', icon: Info, action: () => onNavigate('about-help') },
      ],
    },
  ];

  if (loading) {
    return (
      <div className="min-h-screen bg-gray-50 flex items-center justify-center">
        <Loader2 className="w-8 h-8 text-[#2A79E6] animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header Card */}
      <div className="bg-white px-4 py-6 shadow-sm">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Avatar className="w-16 h-16">
              <AvatarFallback className="bg-[#2A79E6] text-white text-xl">
                {(editName || patientName)[0]}
              </AvatarFallback>
            </Avatar>
            <div>
              {editMode ? (
                <div className="space-y-2">
                  <Input
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                    placeholder="患者姓名"
                    className="text-lg font-semibold h-10 w-32"
                  />
                  <div className="text-sm text-gray-600">
                    {editSurgeryType}术后 · {recoveryPhase}
                  </div>
                </div>
              ) : (
                <div>
                  <h2 className="font-semibold text-lg mb-1">{patientName}</h2>
                  <p className="text-sm text-gray-600">{surgeryType}术后 · {recoveryPhase}</p>
                  {surgeryDate && <p className="text-xs text-gray-400">手术日期：{surgeryDate}</p>}
                </div>
              )}
            </div>
          </div>
          {editMode ? (
            <div className="flex gap-2">
              <Button variant="outline" size="sm" className="min-h-[44px]"
                onClick={() => setEditMode(false)} disabled={saving}>
                <X className="w-4 h-4" />
              </Button>
              <Button size="sm" className="min-h-[44px] bg-[#2A79E6]"
                onClick={handleSave} disabled={saving}>
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              </Button>
            </div>
          ) : (
            <Button variant="outline" size="sm" className="min-h-[44px]"
              onClick={enterEditMode}>
              <Edit3 className="w-4 h-4 mr-1" />编辑信息
            </Button>
          )}
        </div>
      </div>

      {/* Editable Fields Panel */}
      {editMode && (
        <div className="bg-white mx-4 mt-4 rounded-2xl shadow-sm p-5 space-y-4">
          <h3 className="font-semibold text-sm text-gray-700">编辑个人信息</h3>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-gray-500 mb-1 block">年龄</label>
              <Input type="number" value={editAge}
                onChange={(e) => setEditAge(e.target.value)}
                placeholder="年龄" className="min-h-[44px]" />
            </div>
            <div>
              <label className="text-xs text-gray-500 mb-1 block">性别</label>
              <Select value={editGender} onValueChange={setEditGender}>
                <SelectTrigger className="min-h-[44px]"><SelectValue placeholder="选择性别" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="男">男</SelectItem>
                  <SelectItem value="女">女</SelectItem>
                  <SelectItem value="其他">其他</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">手术类型</label>
            <Select value={editSurgeryType} onValueChange={setEditSurgeryType}>
              <SelectTrigger className="min-h-[44px]"><SelectValue placeholder="选择手术类型" /></SelectTrigger>
              <SelectContent>
                <SelectItem value="TKA">TKA（全膝关节置换）</SelectItem>
                <SelectItem value="THA">THA（全髋关节置换）</SelectItem>
                <SelectItem value="ACL">ACL（前交叉韧带重建）</SelectItem>
                <SelectItem value="其他">其他</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">手术日期</label>
            <Input type="date" value={editSurgeryDate}
              onChange={(e) => setEditSurgeryDate(e.target.value)}
              className="min-h-[44px]" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">主治医生</label>
            <Input value={editDoctorName}
              onChange={(e) => setEditDoctorName(e.target.value)}
              placeholder="主治医生姓名" className="min-h-[44px]" />
          </div>
          <div>
            <label className="text-xs text-gray-500 mb-1 block">联系电话</label>
            <Input value={editContact}
              onChange={(e) => setEditContact(e.target.value)}
              placeholder="联系电话" className="min-h-[44px]" />
          </div>
          <Button className="w-full bg-[#2A79E6] hover:bg-[#2267c7] h-12"
            onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin mr-2" /> : <Save className="w-4 h-4 mr-2" />}
            保存修改
          </Button>
        </div>
      )}

      {/* Info summary when not editing */}
      {!editMode && (
        <div className="bg-white mx-4 mt-4 rounded-2xl shadow-sm p-5">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center">
              <Stethoscope className="w-5 h-5 text-[#2A79E6]" />
            </div>
            <div>
              <div className="font-medium text-sm">手术信息</div>
              <div className="text-xs text-gray-500">
                {surgeryType} · {surgeryDate || '未知'} · {String(patientInfo.doctor_name || '未设置')}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Menu Sections */}
      <div className="px-4 pt-6 pb-24 space-y-6">
        {menuItems.map((section, sectionIndex) => (
          <div key={sectionIndex} className="bg-white rounded-2xl shadow-sm overflow-hidden">
            <h3 className="font-semibold px-5 py-4 border-b border-gray-100">{section.section}</h3>
            <div className="divide-y divide-gray-100">
              {section.items.map((item, itemIndex) => {
                const Icon = item.icon;
                // OCR 上传入口使用独立组件
                if ((item as Record<string, unknown>).isUpload) {
                  return <OrderUpload key={itemIndex} />;
                }
                return (
                  <button key={itemIndex}
                    onClick={item.action}
                    className="w-full flex items-center gap-4 px-5 py-4 hover:bg-gray-50 transition-colors min-h-[60px]">
                    <div className="flex-shrink-0 w-10 h-10 bg-blue-50 rounded-full flex items-center justify-center">
                      <Icon className="w-5 h-5 text-[#2A79E6]" />
                    </div>
                    <div className="flex-1 text-left">
                      <div className="font-medium text-sm mb-1">{item.title}</div>
                      <div className="text-xs text-gray-500">{item.subtitle}</div>
                    </div>
                    <ChevronRight className="w-5 h-5 text-gray-400 flex-shrink-0" />
                  </button>
                );
              })}
            </div>
          </div>
        ))}

        <div className="bg-yellow-50 border border-yellow-200 rounded-lg p-4">
          <p className="text-xs text-gray-600 leading-relaxed">
            本应用为AI辅助工具，不能替代专业医疗判断，如遇紧急情况，请立即拨打120就医
          </p>
        </div>
      </div>

      {/* 紧急联系人弹窗 */}
      <EmergencyContactDialog open={showEmergencyContacts} onOpenChange={setShowEmergencyContacts} />
    </div>
  );
}
