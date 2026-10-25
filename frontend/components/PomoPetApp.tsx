'use client';

import { useEffect, useState } from 'react';
import DesktopEnvironment from './DesktopEnvironment';
import PetWindow from './PetWindow';

type WindowRole = 'main' | 'pet';

function readWindowRole(): WindowRole {
  if (typeof window === 'undefined') return 'main';
  const role = (window as Window & { electron?: { windowRole?: WindowRole } }).electron?.windowRole;
  return role === 'pet' ? 'pet' : 'main';
}

export default function PomoPetApp() {
  const [windowRole, setWindowRole] = useState<WindowRole | null>(null);

  useEffect(() => {
    setWindowRole(readWindowRole());
  }, []);

  if (windowRole === null) return null;
  return windowRole === 'pet' ? <PetWindow /> : <DesktopEnvironment />;
}
