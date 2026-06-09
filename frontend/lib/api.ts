const API_BASE = 'http://localhost:8000/api';
const MAX_RETRIES = 3;
const RETRY_DELAY_BASE = 1000;

export class APIError extends Error {
  constructor(
    message: string,
    public status?: number,
    public endpoint?: string,
    public retries = 0
  ) {
    super(message);
    this.name = 'APIError';
  }
}

type ErrorCallback = (error: APIError) => void;
let globalErrorCallback: ErrorCallback | null = null;

export function setErrorCallback(callback: ErrorCallback | null) {
  globalErrorCallback = callback;
}

function notifyError(error: APIError) {
  const logEntry = `[${new Date().toISOString()}] ${error.message} (${error.endpoint})`;
  const existingLog = localStorage.getItem('api_error_log') || '';
  localStorage.setItem('api_error_log', logEntry + '\n' + existingLog);
  console.error(logEntry);
  
  // Send to backend
  fetch(`${API_BASE}/logs/frontend`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      message: error.message,
      endpoint: error.endpoint,
      method: 'GET'
    }),
  }).catch(() => {});
  
  if (globalErrorCallback) {
    globalErrorCallback(error);
  }
}

async function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function fetchAPIWithRetry(
  endpoint: string,
  options: RequestInit = {},
  retries = MAX_RETRIES
): Promise<any> {
  const url = `${API_BASE}${endpoint}`;
  
  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = new APIError(
        `HTTP ${response.status}: ${response.statusText}`,
        response.status,
        endpoint,
        MAX_RETRIES - retries
      );
      
      if (response.status >= 500 && retries > 0) {
        await sleep(RETRY_DELAY_BASE * (MAX_RETRIES - retries));
        return fetchAPIWithRetry(endpoint, options, retries - 1);
      }
      
      notifyError(error);
      throw error;
    }

    return await response.json();
  } catch (error) {
    if (error instanceof APIError) {
      throw error;
    }

    const apiError = new APIError(
      error instanceof Error ? error.message : 'Unknown error',
      undefined,
      endpoint,
      MAX_RETRIES - retries
    );

    if (retries > 0) {
      await sleep(RETRY_DELAY_BASE * (MAX_RETRIES - retries));
      return fetchAPIWithRetry(endpoint, options, retries - 1);
    }

    console.error(`API call failed after ${MAX_RETRIES} retries: ${endpoint}`, apiError);
    notifyError(apiError);
    throw apiError;
  }
}

async function fetchAPI(endpoint: string, options: RequestInit = {}) {
  try {
    return await fetchAPIWithRetry(endpoint, options);
  } catch (error) {
    const logEntry = `[${new Date().toISOString()}] ${options.method || 'GET'} ${endpoint} - ${error}`;
    const existingLog = localStorage.getItem('api_error_log') || '';
    localStorage.setItem('api_error_log', logEntry + '\n' + existingLog);
    console.error(logEntry);
    
    // Send to backend
    try {
      await fetch(`${API_BASE}/logs/frontend`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
          message: String(error),
          endpoint,
          method: options.method || 'GET'
        }),
      });
    } catch {}
    
    return null;
  }
}

export interface Task {
  id: string;
  name: string;
  priority: 'high' | 'medium' | 'low';
  deadline?: string;
  completed: boolean;
  subtasks: { id: string; name: string; completed: boolean }[];
}

export interface Session {
  id: string;
  task_id: string;
  duration: number;
  time_left: number;
  state: 'running' | 'paused' | 'completed' | 'cancelled';
  distraction_count: number;
  started_at: string | null;
}

export interface Statistics {
  focusHoursToday: number;
  focusHoursWeek: number;
  sessionsCompleted: number;
  distractionChain: number;
  distractionData: { time: string; distractions: number }[];
  totalDistractionsWeek: number;
}

export const api = {
  // Task API
  async getTasks(): Promise<Task[]> {
    return fetchAPI('/tasks/');
  },

  async createTask(task: { name: string; priority: string; deadline?: string }): Promise<{ id: string } | null> {
    return fetchAPI('/tasks/', {
      method: 'POST',
      body: JSON.stringify(task),
    });
  },

  async updateTask(taskId: string, task: { name?: string; priority?: string; deadline?: string }): Promise<any> {
    return fetchAPI(`/tasks/${taskId}`, {
      method: 'PUT',
      body: JSON.stringify(task),
    });
  },

  async deleteTask(taskId: string): Promise<any> {
    return fetchAPI(`/tasks/${taskId}`, {
      method: 'DELETE',
    });
  },

  async completeTask(taskId: string): Promise<any> {
    return fetchAPI(`/tasks/${taskId}/complete`, {
      method: 'POST',
    });
  },

  async addSubtask(taskId: string, name: string): Promise<any> {
    return fetchAPI('/tasks/subtasks', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, name }),
    });
  },

  async deleteSubtask(subtaskId: string): Promise<any> {
    return fetchAPI(`/tasks/subtasks/${subtaskId}`, {
      method: 'DELETE',
    });
  },

  // Session API
  async startSession(taskId: string, duration: number): Promise<Session | null> {
    return fetchAPI('/sessions/start', {
      method: 'POST',
      body: JSON.stringify({ task_id: taskId, duration }),
    });
  },

  async pauseSession(): Promise<any> {
    return fetchAPI('/sessions/pause', {
      method: 'POST',
    });
  },

  async resumeSession(): Promise<any> {
    return fetchAPI('/sessions/resume', {
      method: 'POST',
    });
  },

  async cancelSession(): Promise<any> {
    return fetchAPI('/sessions/cancel', {
      method: 'POST',
    });
  },

  async completeSession(): Promise<any> {
    return fetchAPI('/sessions/complete', {
      method: 'POST',
    });
  },

async extendSession(minutes: number): Promise<any> {
     return fetchAPI(`/sessions/extend`, {
       method: 'POST',
       body: JSON.stringify({ minutes }),
     });
   },

  async addDistraction(): Promise<any> {
    return fetchAPI('/sessions/distraction', {
      method: 'POST',
    });
  },

  async updateTimeLeft(timeLeft: number): Promise<any> {
    return fetchAPI('/sessions/update-time', {
      method: 'POST',
      body: JSON.stringify({ time_left: timeLeft }),
    });
  },

  async getCurrentSession(): Promise<Session | null> {
    return fetchAPI('/sessions/current');
  },

  // Statistics API
  async getStatistics(): Promise<Statistics | null> {
    return fetchAPI('/statistics/');
  },

  async getDailyStatistics(): Promise<any> {
    return fetchAPI('/statistics/daily');
  },

  async getWeeklyStatistics(): Promise<any> {
    return fetchAPI('/statistics/weekly');
  },

  async getDistractionStatistics(): Promise<any> {
    return fetchAPI('/statistics/distractions');
  },
};