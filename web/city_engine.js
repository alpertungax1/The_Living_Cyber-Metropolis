/**
 * Technocore Work Graph - The Living Cyber-Metropolis (Isometric Engine)
 * Clean Dialogue Orchestrator, Collision-free Speech Bubbles, Doors & 16-bit Agents.
 */

class SoundEngine {
  constructor() {
    this.ctx = null;
    this.enabled = false;
  }

  init() {
    if (!this.ctx) {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (AudioCtx) this.ctx = new AudioCtx();
    }
  }

  toggle() {
    this.init();
    if (this.ctx && this.ctx.state === 'suspended') {
      this.ctx.resume();
    }
    this.enabled = !this.enabled;
    return this.enabled;
  }

  playTyping() {
    if (!this.enabled || !this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'triangle';
      osc.frequency.setValueAtTime(750 + Math.random() * 350, this.ctx.currentTime);
      gain.gain.setValueAtTime(0.03, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.03);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start();
      osc.stop(this.ctx.currentTime + 0.03);
    } catch (e) {}
  }

  playChime() {
    if (!this.enabled || !this.ctx) return;
    try {
      const notes = [523.25, 659.25, 783.99, 1046.50];
      notes.forEach((freq, idx) => {
        const osc = this.ctx.createOscillator();
        const gain = this.ctx.createGain();
        osc.type = 'sine';
        osc.frequency.setValueAtTime(freq, this.ctx.currentTime + idx * 0.05);
        gain.gain.setValueAtTime(0.05, this.ctx.currentTime + idx * 0.05);
        gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + idx * 0.05 + 0.2);
        osc.connect(gain);
        gain.connect(this.ctx.destination);
        osc.start(this.ctx.currentTime + idx * 0.05);
        osc.stop(this.ctx.currentTime + idx * 0.05 + 0.2);
      });
    } catch (e) {}
  }

  playDoor() {
    if (!this.enabled || !this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'sawtooth';
      osc.frequency.setValueAtTime(220, this.ctx.currentTime);
      osc.frequency.exponentialRampToValueAtTime(440, this.ctx.currentTime + 0.1);
      gain.gain.setValueAtTime(0.02, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.15);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start();
      osc.stop(this.ctx.currentTime + 0.15);
    } catch (e) {}
  }

  playSuccess() {
    if (!this.enabled || !this.ctx) return;
    try {
      const osc = this.ctx.createOscillator();
      const gain = this.ctx.createGain();
      osc.type = 'square';
      osc.frequency.setValueAtTime(440, this.ctx.currentTime);
      osc.frequency.setValueAtTime(880, this.ctx.currentTime + 0.08);
      gain.gain.setValueAtTime(0.04, this.ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.001, this.ctx.currentTime + 0.22);
      osc.connect(gain);
      gain.connect(this.ctx.destination);
      osc.start();
      osc.stop(this.ctx.currentTime + 0.22);
    } catch (e) {}
  }
}

class PixelAgent {
  constructor(id, did, isSigned, name, role = 'worker') {
    this.id = id;
    this.did = did || '';
    this.isSigned = isSigned;
    this.name = name || (isSigned ? did.slice(-8) : id);
    this.role = role;
    this.msgCount = 1;
    this.signedCount = isSigned ? 1 : 0;
    this.item = Math.random() > 0.4 ? (Math.random() > 0.5 ? 'briefcase' : 'laptop') : 'none';

    // Spread agents around city walkways
    // Dynamic, lively walking speed across grid
    this.gridX = 14 + (Math.random() * 12 - 6);
    this.gridY = 14 + (Math.random() * 12 - 6);
    this.targetGridX = this.gridX + (Math.random() * 6 - 3);
    this.targetGridY = this.gridY + (Math.random() * 6 - 3);
    this.speed = 0.065 + Math.random() * 0.04;

    this.state = 'wandering';
    this.insideBuilding = null;
    this.insideTimer = 0;
    this.opacity = 1.0;

    this.palette = this.generatePalette(did || id);
    this.walkCycle = Math.random() * 10;
    this.facing = Math.random() > 0.5 ? 1 : -1;
    this.speechBubble = null;
    this.actionTimer = Math.floor(Math.random() * 30);
  }

  generatePalette(seedStr) {
    let hash = 0;
    for (let i = 0; i < seedStr.length; i++) {
      hash = seedStr.charCodeAt(i) + ((hash << 5) - hash);
    }
    const hairColors = ['#f59e0b', '#ef4444', '#38bdf8', '#10b981', '#a855f7', '#ec4899', '#f97316', '#e2e8f0'];
    const shirtColors = ['#00f2fe', '#38bdf8', '#818cf8', '#c084fc', '#f43f5e', '#34d399', '#fbbf24', '#e11d48'];
    const skinColors = ['#ffd1a4', '#f1c27d', '#e0ac69', '#c68642', '#8d5524', '#ffdfba'];

    return {
      hair: hairColors[Math.abs(hash) % hairColors.length],
      shirt: shirtColors[Math.abs(hash >> 3) % shirtColors.length],
      pants: '#0f172a',
      skin: skinColors[Math.abs(hash >> 6) % skinColors.length]
    };
  }

  setSpeech(text, maxDuration = 220) {
    this.speechBubble = {
      text: text.length > 42 ? text.slice(0, 39) + '...' : text,
      timer: maxDuration,
      maxTimer: maxDuration,
      createdTs: Date.now()
    };
  }

  update(city) {
    // Inside building state
    if (this.state === 'inside_building') {
      this.opacity = Math.max(0, this.opacity - 0.08);
      this.insideTimer--;
      if (this.insideTimer <= 0) {
        this.state = 'wandering';
        if (this.insideBuilding) {
          this.gridX = this.insideBuilding.doorGx;
          this.gridY = this.insideBuilding.doorGy;
          this.targetGridX = this.gridX + (Math.random() * 6 - 3);
          this.targetGridY = this.gridY + (Math.random() * 6 - 3);
        }
        city.sound.playDoor();
        this.item = Math.random() > 0.4 ? 'briefcase' : 'laptop';
      }
      return;
    }

    if (this.state === 'going_to_door') {
      this.opacity = Math.min(1.0, this.opacity + 0.08);
    } else {
      this.opacity = 1.0;
    }

    // Movement towards target
    const dx = this.targetGridX - this.gridX;
    const dy = this.targetGridY - this.gridY;
    const dist = Math.hypot(dx, dy);

    if (dist > 0.12) {
      const stepX = (dx / dist) * this.speed;
      const stepY = (dy / dist) * this.speed;
      const nextX = this.gridX + stepX;
      const nextY = this.gridY + stepY;

      const collides = city.isTileSolid(nextX, nextY, this.insideBuilding);
      if (!collides || this.state === 'going_to_door') {
        this.gridX = nextX;
        this.gridY = nextY;
      } else {
        if (!city.isTileSolid(nextX, this.gridY, this.insideBuilding)) {
          this.gridX = nextX;
        } else if (!city.isTileSolid(this.gridX, nextY, this.insideBuilding)) {
          this.gridY = nextY;
        } else {
          this.targetGridX = 14 + (Math.random() * 14 - 7);
          this.targetGridY = 14 + (Math.random() * 14 - 7);
        }
      }

      this.walkCycle += 0.35;
      this.facing = dx >= 0 ? 1 : -1;
    } else {
      // Reached destination
      if (this.state === 'going_to_door' && this.insideBuilding) {
        this.state = 'inside_building';
        this.insideTimer = 80 + Math.floor(Math.random() * 70); // 1.5 - 2.5s
        city.sound.playDoor();
      } else {
        // Quick wander cycle: pick next destination promptly
        this.actionTimer++;
        if (this.actionTimer > 25 && Math.random() < 0.15) {
          this.actionTimer = 0;
          if (city && city.buildings.length > 0 && Math.random() < 0.6) {
            const bldg = city.buildings[Math.floor(Math.random() * Math.min(city.buildings.length, 5))];
            this.insideBuilding = bldg;
            this.state = 'going_to_door';
            this.targetGridX = bldg.doorGx;
            this.targetGridY = bldg.doorGy;
          } else {
            this.state = 'wandering';
            this.targetGridX = 14 + (Math.random() * 16 - 8);
            this.targetGridY = 14 + (Math.random() * 16 - 8);
          }
        }
      }
    }

    if (this.speechBubble) {
      this.speechBubble.timer--;
      if (this.speechBubble.timer <= 0) {
        this.speechBubble = null;
      }
    }
  }
}

class IsometricCity {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    this.ctx = this.canvas.getContext('2d');
    this.sound = new SoundEngine();

    this.tileWidth = 46;
    this.tileHeight = 23;
    this.gridSize = 30;

    this.scale = 1.0;
    this.offsetX = 0;
    this.offsetY = 0;

    this.buildings = [];
    this.agents = new Map();
    this.particles = [];
    this.hoveredBuilding = null;
    this.selectedEntity = null;

    // Smart Dialogue Orchestrator
    this.maxActiveBubbles = 2; // Strict limit: max 2 speech bubbles at a time across the entire city!
    this.lastSpeechTs = 0;

    this.frame = 0;
    this.rainParticles = [];

    this.initWorld();
    this.initAgentsPopulation();
    this.initEvents();
    this.resize();
    window.addEventListener('resize', () => this.resize());
    this.loop();
  }

  resize() {
    this.canvas.width = this.canvas.parentElement.clientWidth;
    this.canvas.height = this.canvas.parentElement.clientHeight || 470;
    this.offsetX = this.canvas.width / 2;
    this.offsetY = 150;
  }

  initWorld() {
    for (let i = 0; i < 35; i++) {
      this.rainParticles.push({
        x: Math.random() * 1400,
        y: Math.random() * 800,
        speed: 3 + Math.random() * 5,
        len: 8 + Math.random() * 12,
        opacity: 0.12 + Math.random() * 0.2
      });
    }

    this.buildings = [
      {
        id: 'room:lobby',
        name: 'lobby',
        isLandmark: true,
        type: 'landmark',
        gx: 14, gy: 14,
        width: 3, height: 3,
        doorGx: 15.5, doorGy: 17.0,
        doorFacing: 'south',
        heightPx: 110,
        color: '#0369a1',
        accentColor: '#0ea5e9',
        neonGlow: '#00f2fe',
        label: '#LOBBY (Central Plaza)',
        description: 'Technocore Central Hub & Compute Plaza',
        msgs: 0
      },
      {
        id: 'room:d-twg-board',
        name: 'd-twg-board',
        isLandmark: true,
        type: 'board',
        gx: 8, gy: 14,
        width: 2, height: 2,
        doorGx: 9.0, doorGy: 16.0,
        doorFacing: 'south',
        heightPx: 80,
        color: '#b45309',
        accentColor: '#f59e0b',
        neonGlow: '#fbbf24',
        label: '#D-TWG-BOARD',
        description: 'Official Job Board & Attributable Quests',
        msgs: 0
      },
      {
        id: 'room:events',
        name: 'events',
        isLandmark: true,
        type: 'spaceport',
        gx: 20, gy: 14,
        width: 2, height: 2,
        doorGx: 21.0, doorGy: 16.0,
        doorFacing: 'south',
        heightPx: 75,
        color: '#6b21a8',
        accentColor: '#a855f7',
        neonGlow: '#c084fc',
        label: '#EVENTS (Portals)',
        description: 'Room Discovery Gate & Arrival Beacon',
        msgs: 0
      },
      {
        id: 'room:workgraph',
        name: 'workgraph',
        isLandmark: true,
        type: 'observatory',
        gx: 14, gy: 8,
        width: 2, height: 2,
        doorGx: 15.0, doorGy: 10.0,
        doorFacing: 'south',
        heightPx: 90,
        color: '#047857',
        accentColor: '#10b981',
        neonGlow: '#34d399',
        label: '#WORKGRAPH',
        description: 'Topology Radar & Verifiable Metrics',
        msgs: 0
      },
      {
        id: 'room:mb-bunker',
        name: 'mb-mailbox',
        isLandmark: true,
        type: 'mailbox',
        gx: 14, gy: 21,
        width: 2, height: 2,
        doorGx: 15.0, doorGy: 23.0,
        doorFacing: 'south',
        heightPx: 55,
        color: '#9f1239',
        accentColor: '#e11d48',
        neonGlow: '#fb7185',
        label: '#MAILBOX (mb-p-...)',
        description: 'Private Signed Mailbox Terminal',
        msgs: 0
      }
    ];
  }

  isTileSolid(gx, gy, targetBuilding = null) {
    for (const bldg of this.buildings) {
      if (bldg === targetBuilding) {
        if (Math.hypot(gx - bldg.doorGx, gy - bldg.doorGy) < 0.6) return false;
      }
      if (gx >= bldg.gx && gx < bldg.gx + bldg.width && gy >= bldg.gy && gy < bldg.gy + bldg.height) {
        return true;
      }
    }
    return false;
  }

  initAgentsPopulation() {
    const initialAgents = [
      { id: 'did:key:z6MkftWDmuuivktitBVnpZRY8ccVoqrpN1g57M4YbMZPhTCB', isSigned: true, name: 'Keeper-z6Mk…hTCB', role: 'keeper' },
      { id: 'did:key:z6Mkj28A9Xq1bK9Fm7s3L0v4Yp6Z1w2E8uT5rN4cQ7vB', isSigned: true, name: 'Observer-Alpha', role: 'worker' },
      { id: 'did:key:z6Mkp94B7Vc3mN8L1s5K0w2Yq4Z6x1E9uT3rP7cQ2vA', isSigned: true, name: 'Courier-Delta', role: 'worker' },
      { id: 'did:key:z6Mkq15C8Wd4nO9M2t6L1x3Zr5A7y2F0vU4sQ8dR3wB', isSigned: true, name: 'Audit-Agent-7', role: 'worker' },
      { id: 'did:key:z6Mkr26D9Xe5oP0N3u7M2y4As6B8z3G1wV5tR9eS4xC', isSigned: true, name: 'Proof-Builder', role: 'worker' },
      { id: 'did:key:z6Mks37E0Yf6pQ1O4v8N3z5Bt7C9a4H2xW6uS0fT5yD', isSigned: true, name: 'Scout-Flop', role: 'scout' },
      { id: 'did:key:z6Mkt48F1Zg7qR2P5w9O4a6Cu8D0b5I3yX7vT1gU6zE', isSigned: true, name: 'Kibble-Validator', role: 'worker' },
      { id: 'did:key:z6Mku59G2ah8rS3Q6x0P5b7Dv9E1c6J4zY8wU2hV7aF', isSigned: true, name: 'Rep-Tracker', role: 'trader' },
      { id: '~flop-trader', isSigned: false, name: '~flop-trader', role: 'trader' },
      { id: '~kibble-fan', isSigned: false, name: '~kibble-fan', role: 'scout' },
      { id: '~cypher-anon', isSigned: false, name: '~cypher-anon', role: 'scout' },
      { id: '~speedy-bot', isSigned: false, name: '~speedy-bot', role: 'worker' }
    ];

    for (let i = 1; i <= 16; i++) {
      const isSig = i % 2 === 0;
      const fakeDid = isSig ? `did:key:z6Mk${Math.random().toString(36).substring(2, 10)}...` : `~agent_${i}`;
      initialAgents.push({
        id: fakeDid,
        isSigned: isSig,
        name: isSig ? `Agent-z6Mk…${i}` : `~guest_${i}`,
        role: i % 3 === 0 ? 'worker' : 'scout'
      });
    }

    initialAgents.forEach(a => {
      const agent = new PixelAgent(a.id, a.isSigned ? a.id : '', a.isSigned, a.name, a.role);
      this.agents.set(a.id, agent);
    });

    // Start with ONLY 1 clean welcome quote
    const firstAgent = this.agents.values().next().value;
    if (firstAgent) {
      firstAgent.setSpeech("Technocore Work Graph online ⚡", 300);
    }
  }

  isoToScreen(gx, gy, z = 0) {
    const x = (gx - gy) * (this.tileWidth / 2) * this.scale + this.offsetX;
    const y = (gx + gy) * (this.tileHeight / 2) * this.scale + this.offsetY - z * this.scale;
    return { x, y };
  }

  addDiscoveredRoom(roomName) {
    if (this.buildings.some(b => b.name === roomName)) return;

    const angle = Math.random() * Math.PI * 2;
    const radius = 8 + Math.random() * 5;
    const gx = Math.round(14 + Math.cos(angle) * radius);
    const gy = Math.round(14 + Math.sin(angle) * radius);

    const isMailbox = roomName.startsWith('mb-');
    const isEphemeral = roomName.startsWith('e-');
    const isOwned = roomName.startsWith('d-');

    const newBuilding = {
      id: `room:${roomName}`,
      name: roomName,
      isLandmark: false,
      type: isMailbox ? 'mailbox' : isEphemeral ? 'tent' : isOwned ? 'board' : 'standard',
      gx: Math.max(1, Math.min(this.gridSize - 2, gx)),
      gy: Math.max(1, Math.min(this.gridSize - 2, gy)),
      width: 1,
      height: 1,
      doorGx: gx + 0.5,
      doorGy: gy + 1.0,
      doorFacing: 'south',
      heightPx: 35 + Math.random() * 25,
      color: isMailbox ? '#881337' : isEphemeral ? '#9a3412' : '#312e81',
      accentColor: isMailbox ? '#e11d48' : isEphemeral ? '#ea580c' : '#4f46e5',
      neonGlow: isMailbox ? '#f43f5e' : '#818cf8',
      label: `#${roomName}`,
      description: `Public Room (${roomName})`,
      msgs: 1
    };

    this.buildings.push(newBuilding);
    this.spawnPortalBeam(newBuilding.gx, newBuilding.gy, newBuilding.neonGlow);
    this.sound.playChime();
  }

  spawnPortalBeam(gx, gy, color) {
    for (let i = 0; i < 20; i++) {
      this.particles.push({
        gx: gx + (Math.random() - 0.5) * 0.4,
        gy: gy + (Math.random() - 0.5) * 0.4,
        z: 120 + Math.random() * 80,
        vz: -3.5 - Math.random() * 3.5,
        color: color || '#00f2fe',
        size: 2 + Math.random() * 2.5,
        life: 50
      });
    }
  }

  ingestLiveMessage(msg) {
    const sender = msg.from || msg.sender || 'anon';
    const text = msg.text || '';
    const isSigned = sender.startsWith('did:key:');
    const roomName = msg.room || 'lobby';

    let agent = this.agents.get(sender);
    if (!agent) {
      agent = new PixelAgent(sender, isSigned ? sender : '', isSigned, sender);
      this.agents.set(sender, agent);
    }

    agent.msgCount++;
    if (isSigned) agent.signedCount++;

    const targetBldg = this.buildings.find(b => b.name === roomName) || this.buildings[0];
    if (targetBldg) {
      targetBldg.msgs = (targetBldg.msgs || 0) + 1;
      agent.insideBuilding = targetBldg;
      agent.state = 'going_to_door';
      agent.targetGridX = targetBldg.doorGx;
      agent.targetGridY = targetBldg.doorGy;
    }

    // Orchestrate speech: rate-limit speech bubble generation to avoid overlapping clutter
    const now = Date.now();
    if (now - this.lastSpeechTs > 2500) { // Only 1 new speech bubble every 2.5s
      this.clearExcessBubbles();
      agent.setSpeech(text, 240);
      this.lastSpeechTs = now;
      this.sound.playTyping();
    }
  }

  clearExcessBubbles() {
    const activeWithSpeech = [];
    for (const a of this.agents.values()) {
      if (a.speechBubble) {
        activeWithSpeech.push(a);
      }
    }
    // If we have >= maxActiveBubbles, remove the oldest ones
    if (activeWithSpeech.length >= this.maxActiveBubbles) {
      activeWithSpeech.sort((a, b) => a.speechBubble.timer - b.speechBubble.timer);
      while (activeWithSpeech.length >= this.maxActiveBubbles) {
        const oldest = activeWithSpeech.shift();
        oldest.speechBubble = null;
      }
    }
  }

  initEvents() {
    let isDragging = false;
    let startX = 0, startY = 0;

    this.canvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      startX = e.clientX - this.offsetX;
      startY = e.clientY - this.offsetY;
    });

    window.addEventListener('mousemove', (e) => {
      if (isDragging) {
        this.offsetX = e.clientX - startX;
        this.offsetY = e.clientY - startY;
      }

      const rect = this.canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      this.hoveredBuilding = null;
      for (const bldg of this.buildings) {
        const pos = this.isoToScreen(bldg.gx + bldg.width / 2, bldg.gy + bldg.height / 2);
        if (Math.hypot(mx - pos.x, my - (pos.y - bldg.heightPx / 2)) < 30 * this.scale) {
          this.hoveredBuilding = bldg;
          break;
        }
      }
    });

    window.addEventListener('mouseup', () => { isDragging = false; });

    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 1.08 : 0.92;
      this.scale = Math.max(0.5, Math.min(2.2, this.scale * zoomFactor));
    });

    this.canvas.addEventListener('click', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const clickX = e.clientX - rect.left;
      const clickY = e.clientY - rect.top;

      let found = null;
      for (const agent of this.agents.values()) {
        if (agent.opacity < 0.2) continue;
        const pos = this.isoToScreen(agent.gridX, agent.gridY);
        if (Math.hypot(clickX - pos.x, clickY - (pos.y - 18)) < 24 * this.scale) {
          found = { type: 'agent', entity: agent };
          break;
        }
      }

      if (!found) {
        for (const bldg of this.buildings) {
          const pos = this.isoToScreen(bldg.gx + bldg.width / 2, bldg.gy + bldg.height / 2);
          if (Math.hypot(clickX - pos.x, clickY - (pos.y - bldg.heightPx / 2)) < 35 * this.scale) {
            found = { type: 'building', entity: bldg };
            break;
          }
        }
      }

      if (found) {
        this.selectedEntity = found;
        if (found.type === 'agent') {
          found.entity.setSpeech("Inspecting cryptographic credentials...", 240);
        }
        if (window.openCRTInspector) {
          window.openCRTInspector(found);
        }
      }
    });
  }

  drawGrid() {
    this.ctx.lineWidth = 1;
    for (let x = 0; x <= this.gridSize; x += 2) {
      const p1 = this.isoToScreen(x, 0);
      const p2 = this.isoToScreen(x, this.gridSize);
      this.ctx.strokeStyle = 'rgba(30, 41, 59, 0.25)';
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.stroke();
    }
    for (let y = 0; y <= this.gridSize; y += 2) {
      const p1 = this.isoToScreen(0, y);
      const p2 = this.isoToScreen(this.gridSize, y);
      this.ctx.strokeStyle = 'rgba(30, 41, 59, 0.25)';
      this.ctx.beginPath();
      this.ctx.moveTo(p1.x, p1.y);
      this.ctx.lineTo(p2.x, p2.y);
      this.ctx.stroke();
    }
  }

  drawBuilding(bldg) {
    const { gx, gy, width, height, heightPx, color, accentColor, neonGlow, label, isLandmark, doorGx, doorGy } = bldg;

    const p0 = this.isoToScreen(gx, gy);
    const p1 = this.isoToScreen(gx + width, gy);
    const p2 = this.isoToScreen(gx + width, gy + height);
    const p3 = this.isoToScreen(gx, gy + height);

    const h = heightPx * this.scale;
    const r0 = { x: p0.x, y: p0.y - h };
    const r1 = { x: p1.x, y: p1.y - h };
    const r2 = { x: p2.x, y: p2.y - h };
    const r3 = { x: p3.x, y: p3.y - h };

    // Left Wall
    this.ctx.fillStyle = color;
    this.ctx.beginPath();
    this.ctx.moveTo(p0.x, p0.y);
    this.ctx.lineTo(p3.x, p3.y);
    this.ctx.lineTo(r3.x, r3.y);
    this.ctx.lineTo(r0.x, r0.y);
    this.ctx.closePath();
    this.ctx.fill();
    this.ctx.strokeStyle = 'rgba(255,255,255,0.1)';
    this.ctx.stroke();

    // Right Wall
    this.ctx.fillStyle = accentColor;
    this.ctx.beginPath();
    this.ctx.moveTo(p3.x, p3.y);
    this.ctx.lineTo(p2.x, p2.y);
    this.ctx.lineTo(r2.x, r2.y);
    this.ctx.lineTo(r3.x, r3.y);
    this.ctx.closePath();
    this.ctx.fill();
    this.ctx.stroke();

    // Glowing Cyber Doorway
    if (doorGx && doorGy) {
      const doorScreen = this.isoToScreen(doorGx, doorGy);
      this.ctx.save();
      this.ctx.fillStyle = '#0f172a';
      this.ctx.fillRect(doorScreen.x - 5 * this.scale, doorScreen.y - 14 * this.scale, 10 * this.scale, 14 * this.scale);
      this.ctx.strokeStyle = neonGlow;
      this.ctx.shadowColor = neonGlow;
      this.ctx.shadowBlur = 8;
      this.ctx.lineWidth = 1.5;
      this.ctx.strokeRect(doorScreen.x - 5 * this.scale, doorScreen.y - 14 * this.scale, 10 * this.scale, 14 * this.scale);

      this.ctx.fillStyle = neonGlow;
      this.ctx.fillRect(doorScreen.x - 3 * this.scale, doorScreen.y - 12 * this.scale, 6 * this.scale, 2 * this.scale);
      this.ctx.restore();
    }

    // Roof
    this.ctx.fillStyle = '#090d16';
    this.ctx.beginPath();
    this.ctx.moveTo(r0.x, r0.y);
    this.ctx.lineTo(r1.x, r1.y);
    this.ctx.lineTo(r2.x, r2.y);
    this.ctx.lineTo(r3.x, r3.y);
    this.ctx.closePath();
    this.ctx.fill();
    this.ctx.strokeStyle = neonGlow;
    this.ctx.lineWidth = isLandmark ? 2 : 1;
    this.ctx.stroke();

    // Landmark Special Hologram
    if (bldg.type === 'landmark') {
      const topCenter = { x: (r0.x + r2.x) / 2, y: (r0.y + r2.y) / 2 - 20 * this.scale };
      this.ctx.save();
      this.ctx.strokeStyle = '#00f2fe';
      this.ctx.shadowColor = '#00f2fe';
      this.ctx.shadowBlur = 12;
      this.ctx.beginPath();
      this.ctx.arc(topCenter.x, topCenter.y, 9 * this.scale, 0, Math.PI * 2);
      this.ctx.stroke();

      this.ctx.beginPath();
      this.ctx.ellipse(topCenter.x, topCenter.y, 15 * this.scale, 5 * this.scale, this.frame * 0.05, 0, Math.PI * 2);
      this.ctx.stroke();
      this.ctx.restore();
    }

    const isHovered = this.hoveredBuilding === bldg;
    if (isLandmark || isHovered) {
      const centerRoof = { x: (r0.x + r2.x) / 2, y: (r0.y + r2.y) / 2 - 7 * this.scale };
      this.ctx.save();
      this.ctx.font = `bold ${Math.max(9, 10 * this.scale)}px 'Fira Code', monospace`;
      this.ctx.textAlign = 'center';
      this.ctx.fillStyle = '#ffffff';
      this.ctx.shadowColor = neonGlow;
      this.ctx.shadowBlur = 8;
      this.ctx.fillText(label, centerRoof.x, centerRoof.y);
      this.ctx.restore();
    }
  }

  drawAgent(agent) {
    if (agent.opacity <= 0.02) return;

    const pos = this.isoToScreen(agent.gridX, agent.gridY);
    const s = this.scale * 1.5;
    const x = pos.x;
    const y = pos.y;
    const isMoving = agent.state !== 'inside_building';
    const bob = isMoving ? Math.abs(Math.sin(agent.walkCycle)) * 2.5 * s : 0;

    this.ctx.save();
    this.ctx.globalAlpha = agent.opacity;

    // Shadow
    this.ctx.fillStyle = 'rgba(0, 0, 0, 0.55)';
    this.ctx.beginPath();
    this.ctx.ellipse(x, y, (7 + (isMoving ? Math.sin(agent.walkCycle) * 0.8 : 0)) * s, 3.5 * s, 0, 0, Math.PI * 2);
    this.ctx.fill();

    // Legs with clear dynamic walking swing
    const legSwing = Math.sin(agent.walkCycle) * 4.5 * s;
    this.ctx.fillStyle = agent.palette.pants;
    this.ctx.fillRect(x - 3 * s, y - 8 * s + bob, 2.5 * s, 6 * s + legSwing);
    this.ctx.fillRect(x + 0.5 * s, y - 8 * s + bob, 2.5 * s, 6 * s - legSwing);

    // Subtle neon step ripple when walking fast
    if (agent.isSigned && Math.random() < 0.1) {
      this.ctx.strokeStyle = 'rgba(0, 242, 254, 0.3)';
      this.ctx.lineWidth = 1;
      this.ctx.strokeRect(x - 4 * s, y - 2 * s, 8 * s, 2 * s);
    }

    // Torso
    this.ctx.fillStyle = agent.palette.shirt;
    this.ctx.fillRect(x - 4.5 * s, y - 16 * s + bob, 9 * s, 8 * s);

    // Head
    this.ctx.fillStyle = agent.palette.skin;
    this.ctx.fillRect(x - 4 * s, y - 23 * s + bob, 8 * s, 7 * s);

    // Hair
    this.ctx.fillStyle = agent.palette.hair;
    this.ctx.fillRect(x - 4.5 * s, y - 25.5 * s + bob, 9 * s, 3.5 * s);

    // Visor
    this.ctx.fillStyle = agent.isSigned ? '#00f2fe' : '#94a3b8';
    const eyeX = agent.facing === 1 ? x : x - 2.5 * s;
    this.ctx.fillRect(eyeX, y - 20 * s + bob, 2.5 * s, 2 * s);

    // Item
    if (agent.item === 'briefcase') {
      this.ctx.fillStyle = '#fbbf24';
      this.ctx.fillRect(x + 5 * s * agent.facing, y - 13 * s + bob, 4.5 * s, 3.5 * s);
      this.ctx.fillStyle = '#78350f';
      this.ctx.fillRect(x + 5.5 * s * agent.facing, y - 14 * s + bob, 2 * s, 1 * s);
    } else if (agent.item === 'laptop') {
      this.ctx.fillStyle = '#38bdf8';
      this.ctx.fillRect(x + 4 * s * agent.facing, y - 14 * s + bob, 4 * s, 4 * s);
      this.ctx.fillStyle = '#0284c7';
      this.ctx.fillRect(x + 4.5 * s * agent.facing, y - 13.5 * s + bob, 3 * s, 3 * s);
    }

    // Neon Halo
    if (agent.isSigned) {
      this.ctx.strokeStyle = '#00f2fe';
      this.ctx.shadowColor = '#00f2fe';
      this.ctx.shadowBlur = 10;
      this.ctx.lineWidth = 2;
      this.ctx.beginPath();
      this.ctx.ellipse(x, y - 29 * s + bob, 6.5 * s, 2.2 * s, 0, 0, Math.PI * 2);
      this.ctx.stroke();
    }

    // Name Tag
    this.ctx.font = `bold ${Math.max(8, 9 * this.scale)}px 'Fira Code', monospace`;
    this.ctx.textAlign = 'center';
    this.ctx.fillStyle = agent.isSigned ? '#38bdf8' : '#94a3b8';
    this.ctx.fillText(agent.name, x, y - 31 * s + bob);

    // Speech Bubble (Only drawn if active and strictly capped)
    if (agent.speechBubble) {
      const bubbleText = agent.speechBubble.text;
      this.ctx.font = `${Math.max(9, 10 * this.scale)}px 'Fira Code', monospace`;
      const textWidth = this.ctx.measureText(bubbleText).width;
      const bw = textWidth + 16 * this.scale;
      const bh = 20 * this.scale;
      const bx = x - bw / 2;
      const by = y - 48 * s + bob;

      // Card Background with clean shadow
      this.ctx.fillStyle = 'rgba(10, 15, 26, 0.96)';
      this.ctx.strokeStyle = agent.isSigned ? '#00f2fe' : '#64748b';
      this.ctx.shadowColor = agent.isSigned ? '#00f2fe' : 'transparent';
      this.ctx.shadowBlur = 8;
      this.ctx.lineWidth = 1.4;
      this.ctx.beginPath();
      this.ctx.roundRect(bx, by, bw, bh, 4);
      this.ctx.fill();
      this.ctx.stroke();

      // Tail
      this.ctx.beginPath();
      this.ctx.moveTo(x - 3 * this.scale, by + bh);
      this.ctx.lineTo(x, by + bh + 5 * this.scale);
      this.ctx.lineTo(x + 3 * this.scale, by + bh);
      this.ctx.fill();

      // Text
      this.ctx.fillStyle = '#f8fafc';
      this.ctx.shadowBlur = 0;
      this.ctx.fillText(bubbleText, x, by + 13.5 * this.scale);
    }

    this.ctx.restore();
  }

  drawRainAndAtmosphere() {
    this.ctx.save();
    for (const p of this.rainParticles) {
      p.y += p.speed;
      p.x -= p.speed * 0.2;
      if (p.y > this.canvas.height) {
        p.y = -15;
        p.x = Math.random() * this.canvas.width;
      }
      this.ctx.strokeStyle = `rgba(34, 211, 238, ${p.opacity})`;
      this.ctx.lineWidth = 1;
      this.ctx.beginPath();
      this.ctx.moveTo(p.x, p.y);
      this.ctx.lineTo(p.x - p.len * 0.2, p.y + p.len);
      this.ctx.stroke();
    }
    this.ctx.restore();
  }

  render() {
    this.frame++;
    this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);

    const bgGrad = this.ctx.createRadialGradient(
      this.canvas.width / 2, this.canvas.height / 2, 40,
      this.canvas.width / 2, this.canvas.height / 2, this.canvas.width * 0.65
    );
    bgGrad.addColorStop(0, '#0a0f1d');
    bgGrad.addColorStop(1, '#05070e');
    this.ctx.fillStyle = bgGrad;
    this.ctx.fillRect(0, 0, this.canvas.width, this.canvas.height);

    this.drawGrid();

    const renderList = [];

    for (const bldg of this.buildings) {
      renderList.push({
        depth: (bldg.gx + bldg.width) + (bldg.gy + bldg.height),
        draw: () => this.drawBuilding(bldg)
      });
    }

    for (const agent of this.agents.values()) {
      agent.update(this);
      renderList.push({
        depth: agent.gridX + agent.gridY,
        draw: () => this.drawAgent(agent)
      });
    }

    for (let i = this.particles.length - 1; i >= 0; i--) {
      const pt = this.particles[i];
      pt.z += pt.vz;
      pt.life--;
      if (pt.life <= 0 || pt.z <= 0) {
        this.particles.splice(i, 1);
        continue;
      }
      const p = this.isoToScreen(pt.gx, pt.gy, pt.z);
      this.ctx.fillStyle = pt.color;
      this.ctx.beginPath();
      this.ctx.arc(p.x, p.y, pt.size * this.scale, 0, Math.PI * 2);
      this.ctx.fill();
    }

    renderList.sort((a, b) => a.depth - b.depth);
    for (const item of renderList) {
      item.draw();
    }

    this.drawRainAndAtmosphere();
  }

  loop() {
    this.render();
    requestAnimationFrame(() => this.loop());
  }
}

window.IsometricCity = IsometricCity;
window.PixelAgent = PixelAgent;
