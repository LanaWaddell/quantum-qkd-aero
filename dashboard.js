const express = require('express');
const fs = require('fs');
const path = require('path');
const app = express();

const resultsPath = path.join(__dirname, 'outputs', 'results.json');

const imagePaths = [
    { filePath: path.join(__dirname, 'outputs', 'qkd_teleportation.png'), publicPath: '/outputs/qkd_teleportation.png' },
    { filePath: path.join(__dirname, 'qkd_teleportation.png'), publicPath: '/qkd_teleportation.png' },
];

function readResults(callback) {
    fs.readFile(resultsPath, 'utf8', (err, data) => {
        if (err) {
            callback(err);
            return;
        }

        try {
            const results = JSON.parse(data);
            if (results.schema_version !== '2.0') {
                callback(new Error('Unsupported results schema'));
                return;
            }
            callback(null, results);
        } catch (e) {
            callback(e);
        }
    });
}

function normalizeStats(results) {
    return {
        key_yield: results.summary.headline_key_yield,
        fidelity: results.summary.headline_fidelity,
    };
}

function getPlotPath() {
    const plot = imagePaths.find((candidate) => fs.existsSync(candidate.filePath));
    return plot ? plot.publicPath : '/qkd_teleportation.png';
}

// This allows the dashboard to see the PNG file in your folder
app.use(express.static(__dirname));

app.get('/', (req, res) => {
    readResults((err, data) => {
        if (err) {
            res.status(500).send('Run python src/qkd/run.py to generate v2 results.');
            return;
        }

        const stats = normalizeStats(data);
        const plotPath = getPlotPath();

        res.send(`
            <html>
                <body style="font-family: sans-serif; background: #020617; color: #f8fafc; padding: 40px; text-align: center;">
                    <h1 style="color: #38bdf8; margin-bottom: 30px;">🛰️ QKD MISSION CONTROL</h1>
                    
                    <div style="display: flex; justify-content: center; gap: 20px; margin-bottom: 30px;">
                        <div style="background: #1e293b; padding: 20px; border-radius: 10px; border: 1px solid #334155; width: 250px;">
                            <p style="color: #94a3b8; font-size: 0.8em; margin: 0;">SECURE KEY YIELD</p>
                            <h2 style="font-size: 2.5em; color: #4ade80; margin: 10px 0;">${stats.key_yield}</h2>
                        </div>
                        <div style="background: #1e293b; padding: 20px; border-radius: 10px; border: 1px solid #334155; width: 250px;">
                            <p style="color: #94a3b8; font-size: 0.8em; margin: 0;">AVG FIDELITY</p>
                            <h2 style="font-size: 2.5em; color: #fbbf24; margin: 10px 0;">${stats.fidelity}</h2>
                        </div>
                    </div>

                    <div style="background: #1e293b; padding: 20px; border-radius: 10px; border: 1px solid #334155; display: inline-block;">
                        <h3 style="color: #94a3b8; margin-top: 0;">Live Teleportation Link Analysis</h3>
                        <img src="${plotPath}?t=${Date.now()}" style="max-width: 600px; border-radius: 5px; border: 1px solid #475569;">
                    </div>

                    <p style="color: #475569; margin-top: 30px;">Last Sync: ${new Date().toLocaleTimeString()}</p>
                    <script>setTimeout(() => { window.location.reload(); }, 5000);</script>
                </body>
            </html>
        `);
    });
});

app.listen(8080, () => { console.log('✅ Visual Dashboard Live: http://localhost:8080'); });
