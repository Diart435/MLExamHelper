import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import './CreateTestPage.css';

// Импорты API
import apiClient from '../api/client';

/* ===================== ТИПЫ ===================== */

interface MaterialResponse {
  materialId: string;
  courseId: string;
  title: string;
  typeMaterial: string;
  statusMaterial: string;
  sourceUri: string;
  fileType: string;
  materialSize: number;
  createdAt: string;
}

interface MaterialPage {
  content: MaterialResponse[];
  totalElements: number;
  totalPages: number;
  number: number;
  size: number;
  first: boolean;
  last: boolean;
  empty: boolean;
}

interface MaterialUI {
  id: string;
  name: string;
  kind: 'PDF' | 'Текст' | 'Ссылка' | 'Документ';
  status: 'done' | 'progress' | 'error';
  selected: boolean;
}

type QuestionType = 'single_choice' | 'multi_choice' | 'open_answer';

// interface QuestionConfig {
//   type: QuestionType;
//   label: string;
//   count: number | null; // null = "Своё число" не заполнено
// }

/* ===================== API МАТЕРИАЛОВ ===================== */

const materialsApi = {
  getByCourse: async (courseId: string, page = 0, size = 50): Promise<MaterialPage> => {
    const params = new URLSearchParams();
    params.set('courseId', courseId);
    params.set('page', String(page));
    params.set('size', String(size));
    params.set('sort', 'createdAt,desc');
    const res = await apiClient.get<MaterialPage>('/api/materials', { params });
    return res.data;
  },
};

const mapMaterialToUI = (api: MaterialResponse): MaterialUI => {
  const kindMap: Record<string, MaterialUI['kind']> = {
    PDF: 'PDF', TEXT: 'Текст', LINK: 'Ссылка', DOCUMENT: 'Документ', DOCX: 'Документ',
  };
  const statusMap: Record<string, MaterialUI['status']> = {
    DONE: 'done', PROCESSING: 'progress', ERROR: 'error', QUEUED: 'progress',
  };
  return {
    id: api.materialId,
    name: api.title,
    kind: kindMap[api.typeMaterial?.toUpperCase()] ?? 'Документ',
    status: statusMap[api.statusMaterial?.toUpperCase()] ?? 'progress',
    selected: false,
  };
};

/* ===================== КОМПОНЕНТ ===================== */

const CreateTestPage = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();
  
  const [materials, setMaterials] = useState<MaterialUI[]>([]);
  const [loadingMat, setLoadingMat] = useState(true);
  const [testTitle, setTestTitle] = useState('');
  const [customInputs, setCustomInputs] = useState<Record<QuestionType, string>>({
    single_choice: '',
    multi_choice: '',
    open_answer: '',
  });
  const [questionCounts, setQuestionCounts] = useState<Record<QuestionType, number | null>>({
    single_choice: null,
    multi_choice: null,
    open_answer: null,
  });
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  // Загрузка курса и материалов
   const fetchData = useCallback(async () => {
    if (!courseId) {
      navigate('/courses');
      return;
    }

    try {
      setLoadingMat(true);
      // Загружаем только материалы, название курса теперь берется в CabinetLayout
      const materialsData = await materialsApi.getByCourse(courseId);
      setMaterials(materialsData.content.map(mapMaterialToUI));
    } catch (err) {
      console.error('Failed to load data', err);
      setError('Не удалось загрузить данные курса');
    } finally {
      setLoadingMat(false);
    }
  }, [courseId, navigate]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // Обработчики
  const toggleMaterial = (id: string) => {
    setMaterials(prev => prev.map(m => 
      m.id === id ? { ...m, selected: !m.selected } : m
    ));
  };

  const selectQuestionCount = (type: QuestionType, count: number) => {
    setQuestionCounts(prev => ({ ...prev, [type]: count }));
    setCustomInputs(prev => ({ ...prev, [type]: '' }));
  };

  const handleCustomInput = (type: QuestionType, value: string) => {
    const num = parseInt(value);
    setCustomInputs(prev => ({ ...prev, [type]: value }));
    setQuestionCounts(prev => ({ ...prev, [type]: isNaN(num) ? null : num }));
  };

  const handleCreateTest = async () => {
    if (!testTitle.trim()) {
      setError('Введите название теста');
      return;
    }

    const selectedMaterials = materials.filter(m => m.selected && m.status === 'done');
    if (selectedMaterials.length === 0) {
      setError('Выберите хотя бы один обработанный материал');
      return;
    }

    const totalQuestions = Object.values(questionCounts).reduce(
        (sum: number, count) => sum + (count || 0), 
        0
    );
    if (totalQuestions === 0) {
      setError('Укажите количество вопросов хотя бы для одной категории');
      return;
    }

    setCreating(true);
    setError('');

    try {
      // Отправляем запрос на создание теста
      // Пока используем общее количество вопросов, позже можно разделить по типам
      const response = await apiClient.post(`/api/courses/${courseId}/tests/generate`, {
        title: testTitle.trim(),
        mode: 'training',
        timeLimitMinutes: 30,
        materialIds: selectedMaterials.map(m => m.id),
        questionCount: totalQuestions,
        difficulty: 'medium',
      });

      console.log('Test created:', response.data);
      navigate(`/courses/${courseId}`);
    } catch (err: any) {
      console.error('Failed to create test', err);
      setError(err.response?.data?.message || 'Не удалось создать тест');
    } finally {
      setCreating(false);
    }
  };

  const handleCancel = () => {
    navigate(`/courses/${courseId}`);
  };

  const questionTypes: { type: QuestionType; label: string }[] = [
    { type: 'single_choice', label: 'С одним вариантом ответа' },
    { type: 'multi_choice', label: 'Несколько правильных вариантов ответа' },
    { type: 'open_answer', label: 'Короткий ответ - ввести слово или число' },
  ];

  const selectedCount = materials.filter(m => m.selected).length;
  const doneCount = materials.filter(m => m.status === 'done').length;

      return (
        <div className="create-test-page">

          {/* КОНТЕНТ */}
          <div className="create-test-content">
            {/* Левая колонка: Материалы */}
            <div className="materials-column">
              <div className="tabbed-section">
                <h2 className="panel-title tab-header">Материалы</h2>
                <div className="course-panel tabbed-panel">
                  <div className="materials-counter">
                    Выбрано {selectedCount} из {doneCount}
                  </div>

                  {loadingMat ? (
                    <div className="skeleton-loader">Загрузка материалов…</div>
                  ) : materials.length === 0 ? (
                    <div className="empty-state">Нет материалов. Сначала загрузите материалы в курсе.</div>
                  ) : (
                    <div className="materials-list">
                      {materials.map(m => (
                        <div key={m.id} className="material-row">
                          <label className="material-check">
                            <input
                              type="checkbox"
                              checked={m.selected}
                              onChange={() => toggleMaterial(m.id)}
                              disabled={m.status !== 'done'}
                            />
                            <span className="check-box">
                              {m.selected && <span className="check-mark">✓</span>}
                            </span>
                          </label>
                          <div className="material-body">
                            <p className="material-name">{m.name}</p>
                            <span className="material-type">{m.kind}</span>
                          </div>
                          <span className={`badge ${m.status}`}>
                            {m.status === 'done' && 'Обработан'}
                            {m.status === 'progress' && 'В процессе'}
                            {m.status === 'error' && 'Ошибка'}
                          </span>
                          {m.status === 'error' && (
                            <button className="retry-btn" type="button">Повторить</button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Правая колонка: Параметры */}
            <div className="params-column">
              <div className="tabbed-section">
                <h2 className="panel-title tab-header">Параметры</h2>
                <div className="course-panel tabbed-panel">
                  <h3 className="params-title">Новый тест</h3>

                  <div className="param-field">
                    <label className="param-label">Название теста</label>
                    <input
                      type="text"
                      className="param-input"
                      placeholder='Например, "Транзакты и общие знания о Базах Данных"'
                      value={testTitle}
                      onChange={(e) => { setTestTitle(e.target.value); if (error) setError(''); }}
                    />
                  </div>

                  <div className="questions-section">
                    <h4 className="questions-title">Вопросы</h4>

                    {questionTypes.map(({ type, label }) => (
                      <div key={type} className="question-type-block">
                        <p className="question-type-label">{label}</p>
                        <div className="question-buttons">
                          {[5, 15, 20, 25, 30].map(num => (
                            <button
                              key={num}
                              className={`question-btn ${questionCounts[type] === num ? 'active' : ''}`}
                              onClick={() => selectQuestionCount(type, num)}
                            >
                              {num}
                            </button>
                          ))}
                          <div className="custom-input-wrapper">
                            <input
                              type="text"
                              className="custom-input"
                              placeholder="Своё число"
                              value={customInputs[type]}
                              onChange={(e) => handleCustomInput(type, e.target.value)}
                            />
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>

                  {error && <div className="error-message">{error}</div>}

                  <div className="action-buttons">
                    <button className="btn-cancel" onClick={handleCancel} disabled={creating}>
                      Отмена
                    </button>
                    <button className="btn-create" onClick={handleCreateTest} disabled={creating}>
                      {creating ? 'Создание...' : 'Создать тест'}
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      );
};

export default CreateTestPage;