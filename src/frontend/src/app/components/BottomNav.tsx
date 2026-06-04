import { LayoutDashboard, Sparkles, User } from 'lucide-react';
import { PageType } from '../App';

interface BottomNavProps {
  currentPage: PageType;
  onPageChange: (page: PageType) => void;
}

export function BottomNav({ currentPage, onPageChange }: BottomNavProps) {
  const navItems = [
    { id: 'overview' as const, label: '总览', icon: LayoutDashboard },
    { id: 'ai' as const, label: 'AI康复管家', icon: Sparkles },
    { id: 'profile' as const, label: '我的', icon: User },
  ];

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 shadow-lg z-50">
      <div className="flex justify-around items-center h-16 max-w-2xl mx-auto">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentPage === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onPageChange(item.id)}
              className="flex flex-col items-center justify-center flex-1 h-full min-w-[44px] transition-colors"
            >
              <Icon
                className={`w-6 h-6 ${
                  isActive ? 'text-[#2A79E6]' : 'text-gray-500'
                }`}
              />
              <span
                className={`text-xs mt-1 ${
                  isActive ? 'text-[#2A79E6] font-medium' : 'text-gray-500'
                }`}
              >
                {item.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
