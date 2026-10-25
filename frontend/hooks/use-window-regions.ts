import { useEffect } from 'react';

export interface WindowRegion {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface WindowRegionBridge {
  supportsWindowRegions?: boolean;
  setWindowRegions?: (regions: WindowRegion[]) => void;
}

const REGION_SELECTOR = '[data-pomopet-window-region]';
const REGION_PADDING = 17;

function getRegion(element: HTMLElement): WindowRegion | null {
  const style = window.getComputedStyle(element);
  if (
    style.display === 'none'
    || style.visibility === 'hidden'
    || Number.parseFloat(style.opacity || '1') <= 0.01
  ) {
    return null;
  }

  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;

  const left = Math.max(0, Math.floor(rect.left - REGION_PADDING));
  const top = Math.max(0, Math.floor(rect.top - REGION_PADDING));
  const right = Math.min(window.innerWidth, Math.ceil(rect.right + REGION_PADDING));
  const bottom = Math.min(window.innerHeight, Math.ceil(rect.bottom + REGION_PADDING));
  if (right <= left || bottom <= top) return null;

  return { x: left, y: top, width: right - left, height: bottom - top };
}

function getRegionKey(regions: WindowRegion[]) {
  return regions.map(region => (
    `${region.x}:${region.y}:${region.width}:${region.height}`
  )).join('|');
}

export function useWindowRegions(bridge: WindowRegionBridge | undefined, enabled: boolean) {
  useEffect(() => {
    if (!enabled || !bridge?.supportsWindowRegions || !bridge.setWindowRegions) return;

    let animationFrame = 0;
    let lastRegionKey = '';
    let observedElements: HTMLElement[] = [];
    const resizeObserver = new ResizeObserver(() => schedulePublish());
    const attributeObserver = new MutationObserver(() => schedulePublish());

    const publish = () => {
      animationFrame = 0;
      const regions = observedElements
        .map(getRegion)
        .filter((region): region is WindowRegion => region !== null);
      const regionKey = getRegionKey(regions);
      if (regionKey === lastRegionKey) return;

      lastRegionKey = regionKey;
      bridge.setWindowRegions?.(regions);
    };

    function schedulePublish() {
      if (animationFrame) return;
      animationFrame = window.requestAnimationFrame(publish);
    }

    const refreshObservedElements = () => {
      resizeObserver.disconnect();
      attributeObserver.disconnect();
      observedElements = Array.from(document.querySelectorAll<HTMLElement>(REGION_SELECTOR));

      for (const element of observedElements) {
        resizeObserver.observe(element);
        attributeObserver.observe(element, {
          attributes: true,
          attributeFilter: ['class', 'style'],
        });
      }
      schedulePublish();
    };

    const treeObserver = new MutationObserver(refreshObservedElements);
    treeObserver.observe(document.body, { childList: true, subtree: true });
    window.addEventListener('resize', schedulePublish);
    refreshObservedElements();

    return () => {
      if (animationFrame) window.cancelAnimationFrame(animationFrame);
      resizeObserver.disconnect();
      attributeObserver.disconnect();
      treeObserver.disconnect();
      window.removeEventListener('resize', schedulePublish);
      bridge.setWindowRegions?.([]);
    };
  }, [bridge, enabled]);
}
