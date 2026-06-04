{/* 2026-06-01 重构：无患者时显示欢迎引导页，有患者时正常流程 */}
import { useState, useEffect, createContext, useContext } from 'react';
import { Overview } from './components/Overview';
import { AIAssistant } from './components/AIAssistant';
import { Profile } from './components/Profile';
import { CheckIn } from './components/CheckIn';
import { Training } from './components/Training';
import { ProgressDetail } from './components/ProgressDetail';
import { Medication } from './components/Medication';
import { FollowupPlanPage } from './components/FollowupPlan';
import { OrderRecordsPage } from './components/OrderRecords';
import { NotificationSettings, PrivacySecurity, AboutHelp } from './components/SettingsPages';
import { BottomNav } from './components/BottomNav';
import { WelcomePage } from './components/WelcomePage';
import { Toaster } from './components/ui/sonner';
import { getPatient } from '../services/api';

export type PageType = 'overview' | 'ai' | 'profile' | 'checkin' | 'training' | 'progress-detail' | 'medication' | 'followup-plan' | 'order-records' | 'notification-settings' | 'privacy-security' | 'about-help';

interface PatientContextType {
  patientId: string;
  patientName: string;
  setPatientId: (id: string) => void;
  refreshPatient: () => void;
  clearPatient: () => void;
}

export const PatientContext = createContext<PatientContextType>({
  patientId: 'default',
  patientName: '',
  setPatientId: () => {},
  refreshPatient: () => {},
  clearPatient: () => {},
});

export function usePatient() {
  return useContext(PatientContext);
}

function getStoredPatientId(): string {
  return localStorage.getItem('ortho_patient_id') || 'default';
}

export default function App() {
  const [currentPage, setCurrentPage] = useState<PageType>('overview');
  const [patientId, setPatientIdState] = useState(getStoredPatientId);
  const [patientName, setPatientName] = useState('');

  // 持久化 patientId
  useEffect(() => {
    localStorage.setItem('ortho_patient_id', patientId);
  }, [patientId]);

  // 加载患者姓名
  useEffect(() => {
    if (patientId && patientId !== 'default') {
      getPatient(patientId)
        .then((p) => { if (p?.name) setPatientName(p.name); else setPatientName(''); })
        .catch(() => setPatientName(''));
    } else {
      setPatientName('');
    }
  }, [patientId]);

  const setPatientId = (id: string) => {
    setPatientIdState(id);
    setCurrentPage('overview');
  };

  const clearPatient = () => {
    setPatientIdState('default');
    setPatientName('');
    setCurrentPage('overview');
  };

  const refreshPatient = () => {
    if (patientId && patientId !== 'default') {
      getPatient(patientId)
        .then((p) => { if (p?.name) setPatientName(p.name); })
        .catch(() => {});
    }
  };

  const handlePatientSelected = (id: string, name: string) => {
    setPatientIdState(id);
    setPatientName(name || '');
    setCurrentPage('overview');
  };

  // ── 无患者选中 → 欢迎引导页 ──────────────────

  if (patientId === 'default') {
    return (
      <PatientContext.Provider value={{ patientId, patientName, setPatientId, refreshPatient, clearPatient }}>
        <WelcomePage onPatientSelected={handlePatientSelected} />
        <Toaster />
      </PatientContext.Provider>
    );
  }

  // ── 有患者选中 → 正常应用流程 ────────────────

  const renderPage = () => {
    switch (currentPage) {
      case 'overview':
        return <Overview onNavigate={setCurrentPage} />;
      case 'ai':
        return <AIAssistant />;
      case 'profile':
        return <Profile onNavigate={setCurrentPage} />;
      case 'checkin':
        return <CheckIn onBack={() => setCurrentPage('overview')} />;
      case 'training':
        return <Training onBack={() => setCurrentPage('overview')} />;
      case 'progress-detail':
        return <ProgressDetail onBack={() => setCurrentPage('overview')} />;
      case 'medication':
        return <Medication onBack={() => setCurrentPage('overview')} />;
      case 'followup-plan':
        return <FollowupPlanPage onBack={() => setCurrentPage('profile')} />;
      case 'order-records':
        return <OrderRecordsPage onBack={() => setCurrentPage('profile')} />;
      case 'notification-settings':
        return <NotificationSettings onBack={() => setCurrentPage('profile')} />;
      case 'privacy-security':
        return <PrivacySecurity onBack={() => setCurrentPage('profile')} />;
      case 'about-help':
        return <AboutHelp onBack={() => setCurrentPage('profile')} />;
      default:
        return <Overview onNavigate={setCurrentPage} />;
    }
  };

  const hideBottomNav = ['checkin', 'training', 'progress-detail'].includes(currentPage);

  return (
    <PatientContext.Provider value={{ patientId, patientName, setPatientId, refreshPatient, clearPatient }}>
      <div className="size-full flex flex-col bg-gray-50">
        <div className="flex-1 overflow-y-auto pb-20">
          {renderPage()}
        </div>
        <Toaster />
        {!hideBottomNav && (
          <BottomNav currentPage={currentPage} onPageChange={setCurrentPage} />
        )}
      </div>
    </PatientContext.Provider>
  );
}
