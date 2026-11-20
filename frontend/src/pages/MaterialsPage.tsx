import { useRef, useState, type ChangeEvent, type DragEvent } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import './MaterialsPage.css';

const MAX_FILE_SIZE = 50 * 1024 * 1024;

const UploadIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M12 16V5m0 0L7.5 9.5M12 5l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    <path d="M4 15.5v2A2.5 2.5 0 006.5 20h11a2.5 2.5 0 002.5-2.5v-2" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);

const SearchIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.8" />
    <path d="M16 16l4.5 4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
  </svg>
);

const RefreshIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <path d="M20 12a8 8 0 11-2.34-5.66M20 4v4.5h-4.5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const DocIcon = () => (
  <svg viewBox="0 0 36 44" fill="none" aria-hidden="true">
    <path d="M7 3.5h14.5L30 12v27a2 2 0 01-2 2H7a2 2 0 01-2-2v-33a2 2 0 012-2z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    <path d="M21.5 3.5V12H30" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
    <path d="M10.5 20h14M10.5 26h14M10.5 32h9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
  </svg>
);

const EmptyIcon = () => (
  <svg viewBox="0 0 64 64" fill="none" aria-hidden="true">
    <path d="M14 10h24l12 12v32a4 4 0 01-4 4H14a4 4 0 01-4-4V14a4 4 0 014-4z" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M38 10v12h12" stroke="currentColor" strokeWidth="2.4" strokeLinejoin="round" />
    <path d="M20 34h20M20 42h20M20 50h12" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" />
  </svg>
);

const formatSize = (bytes: number): string => {
  if (!bytes || bytes < 0) return '—';
  const units = ['Б', 'КБ', 'МБ', 'ГБ'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = value >= 10 || unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
};

const MaterialsPage = () => {
  const { courseId } = useParams<{ courseId: string }>();
  const navigate = useNavigate();

  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // UI состояния панели материалов (данные и логика фильтрации подключаются далее)
  const [query, setQuery] = useState('');
  const materialsCount = 0;

  const onPickClick = () => fileInputRef.current?.click();

  const addFiles = (files: FileList | File[]) => {
    const incoming = Array.from(files);
    if (!incoming.length) return;
    const accepted: File[] = [];
    const problems: string[] = [];
    incoming.forEach((file) => {
      const extension = file.name.split('.').pop()?.toLowerCase() ?? '';
      if (extension !== 'pdf' && extension !== 'docx') problems.push(`${file.name} — только PDF или DOCX`);
      else if (file.size === 0) problems.push(`${file.name} — пустой файл`);
      else if (file.size > MAX_FILE_SIZE) problems.push(`${file.name} — больше 50 МБ`);
      else accepted.push(file);
    });
    if (accepted.length) {
      setPendingFiles((prev) => [...prev, ...accepted]);
      setUploadNotice(null);
    }
    setUploadError(problems.length ? problems.join('; ') : null);
  };

  const removePendingFile = (index: number) => setPendingFiles((prev) => prev.filter((_, i) => i !== index));
  const handleFileInput = (event: ChangeEvent<HTMLInputElement>) => {
    if (event.target.files) addFiles(event.target.files);
    event.target.value = '';
  };
  const handleDragOver = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); if (!dragActive) setDragActive(true); };
  const handleDragLeave = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const nextTarget = event.relatedTarget as Node | null;
    if (nextTarget && event.currentTarget.contains(nextTarget)) return;
    setDragActive(false);
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault(); setDragActive(false);
    if (event.dataTransfer.files) addFiles(event.dataTransfer.files);
  };
  const handleUpload = () => {
    if (!pendingFiles.length) return;
    setUploadNotice(`Подготовлено файлов: ${pendingFiles.length}. Отправка на сервер будет подключена на этапе интеграции с API.`);
    setUploadError(null);
  };

  if (!courseId) {
    return (
      <div className="materials-page">
        <div className="materials-page__pattern" aria-hidden="true" />
        <div className="materials-page__content">
          <div className="materials-state is-error">
            <p>Курс не найден</p>
            <span>Вернитесь к списку курсов и откройте материалы нужного курса.</span>
            <button type="button" className="materials-state__retry" onClick={() => navigate('/courses')}>Ко всем курсам</button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="materials-page">
      <div className="materials-page__pattern" aria-hidden="true" />
      <div className="materials-page__content">
        <section className="materials-block">
          <div className="materials-tab">Загрузка материала</div>
          <div className="materials-panel materials-panel--upload">
            <div
              className={`upload-zone${dragActive ? ' is-dragging' : ''}`}
              onClick={onPickClick}
              onDragEnter={handleDragOver}
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <input ref={fileInputRef} type="file" accept=".pdf,.docx,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document" multiple className="upload-zone__input" onChange={handleFileInput} tabIndex={-1} />
              <span className="upload-zone__icon"><UploadIcon /></span>
              <h2 className="upload-zone__title">Загрузите материалы</h2>
              <p className="upload-zone__hint">Перетащите файлы сюда или выберите на устройстве</p>
              <p className="upload-zone__formats">PDF или DOCX · до 50 МБ</p>
              {pendingFiles.length > 0 && (
                <ul className="upload-zone__files" onClick={(e) => e.stopPropagation()}>
                  {pendingFiles.map((file, index) => (
                    <li key={`${file.name}-${file.lastModified}-${index}`} className="upload-zone__file">
                      <span className="upload-zone__file-name" title={file.name}>{file.name}</span>
                      <span className="upload-zone__file-size">{formatSize(file.size)}</span>
                      <button type="button" className="upload-zone__file-remove" onClick={() => removePendingFile(index)} aria-label={`Убрать ${file.name}`}>×</button>
                    </li>
                  ))}
                </ul>
              )}
              <div className="upload-zone__actions" onClick={(e) => e.stopPropagation()}>
                <button type="button" className="materials-btn materials-btn--outline" onClick={onPickClick}>Выберите файлы</button>
                {pendingFiles.length > 0 && (
                  <button type="button" className="materials-btn materials-btn--primary" onClick={handleUpload}>
                    Загрузить{pendingFiles.length > 1 ? ` (${pendingFiles.length})` : ''}
                  </button>
                )}
              </div>
            </div>
            {(uploadError || uploadNotice) && (
              <div className={`upload-message${uploadError ? ' is-error' : ' is-success'}`} role="status">{uploadError ?? uploadNotice}</div>
            )}
          </div>
        </section>

        <section className="materials-block">
          <div className="materials-tab">
            Материалы
            <span className="materials-tab__count">{materialsCount}</span>
          </div>

          <div className="materials-panel materials-panel--list">
            <div className="materials-filters">
              <label className="materials-search">
                <span className="materials-search__icon"><SearchIcon /></span>
                <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по названию" aria-label="Поиск материалов по названию" />
              </label>
              <select className="materials-filter" defaultValue="ALL" aria-label="Фильтр по типу материала">
                <option value="ALL">Все типы</option>
                <option value="PDF">PDF</option>
                <option value="DOCX">DOCX</option>
              </select>
              <select className="materials-filter" defaultValue="ALL" aria-label="Фильтр по статусу материала">
                <option value="ALL">Все статусы</option>
                <option value="READY">Обработан</option>
                <option value="PROCESSING">В процессе</option>
                <option value="ERROR">Ошибка</option>
              </select>
              <select className="materials-filter" defaultValue="newest" aria-label="Сортировка материалов">
                <option value="newest">Сначала новые</option>
                <option value="oldest">Сначала старые</option>
                <option value="title">По названию</option>
                <option value="size">По размеру</option>
              </select>
              <button type="button" className="materials-filter materials-filter--reset" disabled>Сбросить фильтры</button>
            </div>

            <div className="materials-toolbar">
              <div className="materials-toolbar__search">
                <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Поиск по названию" aria-label="Быстрый поиск материалов" />
              </div>
              <button type="button" className="materials-toolbar__apply" title="Обновить список">
                <span className="materials-toolbar__apply-icon"><RefreshIcon /></span>
                Обновить
              </button>
            </div>

            <div className="materials-table-wrap">
              <table className="materials-table">
                <thead>
                  <tr>
                    <th className="col-check"><input type="checkbox" aria-label="Выбрать все материалы" disabled /></th>
                    <th>Название</th>
                    <th className="col-type">Тип</th>
                    <th className="col-size">Размер</th>
                    <th className="col-date">Дата загрузки</th>
                    <th className="col-status">Статус</th>
                    <th className="col-actions">Действия</th>
                  </tr>
                </thead>
                <tbody />
              </table>
              <div className="materials-state">
                <span className="materials-state__icon"><EmptyIcon /></span>
                <p>Материалов пока нет</p>
                <span>Загрузите первый PDF или DOCX — он появится в этом списке.</span>
              </div>
            </div>

            <div className="materials-panel__footer">
              <span>Показано 0 из 0</span>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
};

export default MaterialsPage;
