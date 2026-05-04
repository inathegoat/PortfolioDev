document.addEventListener('DOMContentLoaded', () => {
    // ─── Navigation Logic ──────────────────────────────────────────────────
    const navItems = document.querySelectorAll('.nav-item');
    const viewSections = document.querySelectorAll('.view-section');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            // Remove active class from all
            navItems.forEach(nav => nav.classList.remove('active'));
            viewSections.forEach(section => section.classList.remove('active'));
            
            // Add active class to clicked
            item.classList.add('active');
            
            // Show corresponding view
            const targetId = item.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
            
            // Refresh data based on view
            if (targetId === 'view-overview') fetchStats();
            if (targetId === 'view-tasks') fetchTasks();
            if (targetId === 'view-goals') fetchGoals();
            if (targetId === 'view-documents') fetchDocuments();
            if (targetId === 'view-graph') fetchGraph();
        });
    });

    // ─── API Fetchers ──────────────────────────────────────────────────────

    function fetchStats() {
        fetch('/api/stats')
            .then(res => res.json())
            .then(data => {
                document.getElementById('stat-memories').textContent = data.memory_count;
                document.getElementById('stat-tasks-pending').textContent = data.pending_tasks;
                document.getElementById('stat-tasks-done').textContent = data.completed_tasks;
                document.getElementById('stat-goals').textContent = data.goal_count;
                
                // Update Agent Toggle
                const toggle = document.getElementById('agent-toggle');
                const statusTxt = document.getElementById('agent-status');
                toggle.checked = data.agent_running;
                if (data.agent_running) {
                    statusTxt.textContent = "Actif";
                    statusTxt.className = "status-indicator status-on";
                } else {
                    statusTxt.textContent = "Arrêté";
                    statusTxt.className = "status-indicator status-off";
                }
            })
            .catch(err => console.error("Error fetching stats:", err));
            
        fetch('/api/memories')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('recent-memories-list');
                container.innerHTML = '';
                
                if (data.memories.length === 0) {
                    container.innerHTML = '<p style="padding: 20px; color: #94a3b8;">Aucune mémoire trouvée.</p>';
                    return;
                }
                
                data.memories.forEach(mem => {
                    const el = document.createElement('div');
                    el.style.padding = "16px";
                    el.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
                    
                    const date = mem.timestamp ? new Date(mem.timestamp).toLocaleString() : 'Inconnu';
                    
                    el.innerHTML = `
                        <div style="font-size: 12px; color: var(--accent-color); margin-bottom: 4px;">${date}</div>
                        <div style="font-weight: 500; margin-bottom: 8px;">Q: ${mem.question}</div>
                        <div style="font-size: 14px; color: var(--text-secondary); line-height: 1.4;">A: ${mem.answer.substring(0, 150)}...</div>
                    `;
                    container.appendChild(el);
                });
            });
    }

    function fetchGoals() {
        fetch('/api/goals')
            .then(res => res.json())
            .then(data => {
                const container = document.getElementById('goals-grid');
                container.innerHTML = '';
                
                if (data.goals.length === 0) {
                    container.innerHTML = '<p>Aucun objectif défini.</p>';
                    return;
                }
                
                data.goals.forEach(goal => {
                    const el = document.createElement('div');
                    el.className = 'goal-card';
                    el.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                            <div style="display: flex; gap: 8px; align-items: center;">
                                <h3 style="margin: 0;">${goal.title}</h3>
                                <button onclick="deleteGoal('${goal.id}')" style="background: none; border: none; color: var(--danger-color); cursor: pointer; padding: 4px;" title="Supprimer">
                                    <i class="fa-solid fa-xmark"></i>
                                </button>
                            </div>
                            <span style="font-size: 12px; background: rgba(59,130,246,0.2); color: var(--accent-color); padding: 4px 8px; border-radius: 12px; font-weight: 600;">Priorité ${goal.priority}/10</span>
                        </div>
                        <p>${goal.description || 'Pas de description'}</p>
                        <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">Progression: ${goal.progress || 0}%</div>
                        <div class="progress-bar">
                            <div class="progress-fill" style="width: ${goal.progress || 0}%"></div>
                        </div>
                    `;
                    container.appendChild(el);
                });
            });
    }

    function fetchTasks() {
        fetch('/api/tasks')
            .then(res => res.json())
            .then(data => {
                const todoList = document.getElementById('task-list-todo');
                const progList = document.getElementById('task-list-progress');
                const doneList = document.getElementById('task-list-done');
                
                todoList.innerHTML = '';
                progList.innerHTML = '';
                doneList.innerHTML = '';
                
                data.tasks.forEach(task => {
                    const el = document.createElement('div');
                    el.className = 'task-item';
                    el.innerHTML = `
                        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
                            <div style="display: flex; gap: 8px; align-items: center;">
                                <h4 style="margin:0;">${task.title}</h4>
                                <button onclick="deleteTask('${task.id}')" style="background: none; border: none; color: var(--danger-color); cursor: pointer; padding: 2px;" title="Supprimer">
                                    <i class="fa-solid fa-xmark"></i>
                                </button>
                            </div>
                            <span style="font-size: 10px; color: var(--accent-color);">P${task.priority}</span>
                        </div>
                        <p>${task.description || ''}</p>
                    `;
                    
                    const status = task.status || 'todo';
                    if (status === 'todo' || status === 'pending') {
                        todoList.appendChild(el);
                    } else if (status === 'in_progress') {
                        progList.appendChild(el);
                    } else if (status === 'completed' || status === 'done') {
                        doneList.appendChild(el);
                    }
                });
            });
    }

    function fetchDocuments() {
        fetch('/api/documents')
            .then(res => res.json())
            .then(data => {
                const tbody = document.getElementById('documents-list');
                tbody.innerHTML = '';
                
                if (data.documents.length === 0) {
                    tbody.innerHTML = '<tr><td colspan="4" style="padding: 12px;">Aucun document dans la base de données.</td></tr>';
                    return;
                }
                
                // Sort by ingested date, newest first
                data.documents.sort((a, b) => new Date(b.ingested_at || 0) - new Date(a.ingested_at || 0));
                
                data.documents.forEach(doc => {
                    const tr = document.createElement('tr');
                    tr.style.borderBottom = "1px solid rgba(255,255,255,0.05)";
                    
                    const statusColor = doc.status === 'ingested' ? 'var(--success-color)' : 
                                      (doc.status === 'error' ? 'var(--danger-color)' : 'var(--warning-color)');
                    
                    const date = doc.ingested_at ? new Date(doc.ingested_at).toLocaleString() : 'Inconnu';
                    
                    tr.innerHTML = `
                        <td style="padding: 12px; font-weight: 500;">
                            ${doc.filename}
                            <button onclick="deleteDocument('${doc.id}')" style="background: none; border: none; color: var(--danger-color); cursor: pointer; padding: 4px; margin-left: 8px;" title="Supprimer">
                                <i class="fa-solid fa-xmark"></i>
                            </button>
                        </td>
                        <td style="padding: 12px; color: var(--text-secondary);"><span style="background: rgba(255,255,255,0.1); padding: 4px 8px; border-radius: 4px; font-size: 12px;">${doc.file_type}</span></td>
                        <td style="padding: 12px;"><span style="color: ${statusColor};"><i class="fa-solid fa-circle" style="font-size: 8px; margin-right: 6px;"></i>${doc.status}</span></td>
                        <td style="padding: 12px; color: var(--text-secondary); font-size: 14px;">${date}</td>
                    `;
                    tbody.appendChild(tr);
                });
            })
            .catch(err => console.error("Error fetching documents:", err));
    }

    // ─── Delete Actions ──────────────────────────────────────────────────
    
    window.deleteGoal = function(id) {
        if (!confirm("Voulez-vous vraiment supprimer cet objectif ?")) return;
        fetch('/api/goals/' + id, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => { fetchGoals(); fetchStats(); })
            .catch(err => console.error(err));
    };

    window.deleteTask = function(id) {
        if (!confirm("Voulez-vous vraiment supprimer cette tâche ?")) return;
        fetch('/api/tasks/' + id, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => { fetchTasks(); fetchStats(); })
            .catch(err => console.error(err));
    };

    window.deleteDocument = function(id) {
        if (!confirm("Voulez-vous vraiment supprimer ce document ?")) return;
        fetch('/api/documents/' + id, { method: 'DELETE' })
            .then(res => res.json())
            .then(data => { fetchDocuments(); fetchStats(); })
            .catch(err => console.error(err));
    };

    // ─── File Upload Logic ────────────────────────────────────────────────

    const fileUpload = document.getElementById('file-upload');
    if (fileUpload) {
        fileUpload.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            // Show optimistic UI loading
            const label = document.querySelector('label[for="file-upload"]');
            const originalText = label.innerHTML;
            label.innerHTML = '<i class="fa-solid fa-circle-notch fa-spin" style="margin-right: 8px;"></i> Upload en cours...';
            
            const formData = new FormData();
            formData.append('file', file);
            
            fetch('/api/upload', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                label.innerHTML = '<i class="fa-solid fa-check" style="margin-right: 8px;"></i> Terminé';
                setTimeout(() => {
                    label.innerHTML = originalText;
                    fetchDocuments(); // Refresh list to show pending
                    fetchStats();
                }, 2000);
            })
            .catch(err => {
                console.error(err);
                label.innerHTML = '<i class="fa-solid fa-triangle-exclamation" style="margin-right: 8px;"></i> Erreur';
                setTimeout(() => { label.innerHTML = originalText; }, 3000);
            });
            
            // Reset input
            e.target.value = '';
        });
    }

    // ─── Graph Logic ───────────────────────────────────────────────────────
    let network = null;
    
    function fetchGraph() {
        const container = document.getElementById('network-container');
        container.innerHTML = '<div class="loading-spinner" style="display:flex; justify-content:center; align-items:center; height:100%;"><i class="fa-solid fa-circle-notch fa-spin fa-2x"></i></div>';
        
        fetch('/api/graph')
            .then(res => res.json())
            .then(data => {
                container.innerHTML = '';
                
                const nodes = new vis.DataSet(data.nodes);
                const edges = new vis.DataSet(data.edges);
                
                const graphData = { nodes: nodes, edges: edges };
                const options = {
                    nodes: {
                        font: { color: '#ffffff' },
                        borderWidth: 2,
                        shadow: true
                    },
                    edges: {
                        color: { color: 'rgba(255,255,255,0.2)', highlight: 'rgba(255,255,255,0.8)' },
                        width: 1,
                        smooth: { type: 'continuous' }
                    },
                    physics: {
                        barnesHut: { gravitationalConstant: -2000, centralGravity: 0.3, springLength: 150 },
                        stabilization: { iterations: 150 }
                    },
                    groups: {
                        goals: { color: { background: '#ef4444', border: '#b91c1c' } },
                        tasks: { color: { background: '#3b82f6', border: '#1d4ed8' } },
                        docs: { color: { background: '#10b981', border: '#047857' } }
                    }
                };
                
                if (network) network.destroy();
                network = new vis.Network(container, graphData, options);
            })
            .catch(err => {
                console.error("Error fetching graph:", err);
                container.innerHTML = '<p style="color:#ef4444; padding:20px;">Erreur de chargement de la constellation.</p>';
            });
    }

    // ─── Chat Logic ────────────────────────────────────────────────────────

    const chatInput = document.getElementById('chat-input');
    const btnSend = document.getElementById('btn-send-chat');
    const chatHistory = document.getElementById('chat-history');

    function appendMessage(text, isUser = false) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `chat-message ${isUser ? 'user-message' : 'ai-message'}`;
        
        const icon = isUser ? 'fa-user' : 'fa-brain';
        
        // Use marked.parse if available (for markdown), else plain text
        let contentHTML = text;
        if (typeof marked !== 'undefined') {
            contentHTML = marked.parse(text);
        } else {
            contentHTML = text.replace(/\\n/g, '<br>');
        }
        
        msgDiv.innerHTML = `
            <div class="avatar"><i class="fa-solid ${icon}"></i></div>
            <div class="bubble">${contentHTML}</div>
        `;
        
        chatHistory.appendChild(msgDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        
        // Typeset math if MathJax is loaded
        if (window.MathJax && window.MathJax.typesetPromise) {
            MathJax.typesetPromise([msgDiv]).catch((err) => console.log(err.message));
        }
    }

    function sendMessage() {
        const text = chatInput.value.trim();
        if (!text) return;
        
        appendMessage(text, true);
        chatInput.value = '';
        
        const useInternet = document.getElementById('internet-toggle').checked;
        
        // Show typing indicator
        const typingId = "typing-" + Date.now();
        const typingDiv = document.createElement('div');
        typingDiv.className = 'chat-message ai-message';
        typingDiv.id = typingId;
        typingDiv.innerHTML = `
            <div class="avatar"><i class="fa-solid fa-brain"></i></div>
            <div class="bubble"><i class="fa-solid fa-ellipsis fa-fade"></i></div>
        `;
        chatHistory.appendChild(typingDiv);
        chatHistory.scrollTop = chatHistory.scrollHeight;
        
        fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ question: text, use_internet: useInternet })
        })
        .then(res => res.json())
        .then(data => {
            document.getElementById(typingId).remove();
            if (data.error) {
                appendMessage("Erreur: " + data.error);
            } else {
                appendMessage(data.answer);
            }
        })
        .catch(err => {
            document.getElementById(typingId).remove();
            appendMessage("Erreur de connexion au serveur local.");
        });
    }

    btnSend.addEventListener('click', sendMessage);
    chatInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    // ─── Agent Toggle Logic ────────────────────────────────────────────────

    const agentToggle = document.getElementById('agent-toggle');
    const agentStatus = document.getElementById('agent-status');

    agentToggle.addEventListener('change', (e) => {
        // Optimistic UI update
        if (e.target.checked) {
            agentStatus.textContent = "Démarrage...";
            agentStatus.className = "status-indicator status-on";
        } else {
            agentStatus.textContent = "Arrêt...";
            agentStatus.className = "status-indicator status-off";
        }
        
        fetch('/api/agent/toggle', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        })
        .then(res => {
            if (!res.ok) throw new Error("Erreur serveur");
            return res.json();
        })
        .then(data => {
            agentToggle.checked = data.running;
            if (data.running) {
                agentStatus.textContent = "Actif";
                agentStatus.className = "status-indicator status-on";
            } else {
                agentStatus.textContent = "Arrêté";
                agentStatus.className = "status-indicator status-off";
            }
        })
        .catch(err => {
            console.error(err);
            // Revert on error
            const isCheckedNow = !e.target.checked;
            agentToggle.checked = isCheckedNow;
            if (isCheckedNow) {
                agentStatus.textContent = "Actif";
                agentStatus.className = "status-indicator status-on";
            } else {
                agentStatus.textContent = "Arrêté";
                agentStatus.className = "status-indicator status-off";
            }
        });
    });

    // Initial Load
    fetchStats();
});
