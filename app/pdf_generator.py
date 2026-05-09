from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
from datetime import datetime

class PDFReportGenerator:
    def __init__(self):
        self.styles = getSampleStyleSheet()
        self._setup_custom_styles()
    
    def _setup_custom_styles(self):
        self.styles.add(ParagraphStyle(
            name='CustomTitle',
            parent=self.styles['Heading1'],
            fontSize=24,
            textColor=colors.HexColor('#1e40af'),
            spaceAfter=12,
            alignment=TA_CENTER,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='SectionHeader',
            parent=self.styles['Heading2'],
            fontSize=16,
            textColor=colors.HexColor('#1e293b'),
            spaceAfter=10,
            spaceBefore=15,
            fontName='Helvetica-Bold'
        ))
        
        self.styles.add(ParagraphStyle(
            name='BodyText',
            parent=self.styles['Normal'],
            fontSize=11,
            textColor=colors.HexColor('#334155'),
            spaceAfter=8
        ))
    
    def generate_report(self, analysis_data: dict) -> BytesIO:
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.75*inch, bottomMargin=0.75*inch)
        story = []
        
        try:
            # Cover Section
            story.append(Paragraph("AI Powered Resume Analyzer", self.styles['CustomTitle']))
            story.append(Paragraph("Detailed Resume Evaluation Report", self.styles['Heading3']))
            story.append(Spacer(1, 0.3*inch))
            
            # Date and Score
            date_str = datetime.now().strftime("%B %d, %Y")
            story.append(Paragraph(f"<b>Generated:</b> {date_str}", self.styles['BodyText']))
            
            if 'overall_score' in analysis_data:
                story.append(Paragraph(f"<b>Overall Score:</b> <font size=18 color='#3b82f6'>{analysis_data['overall_score']}%</font>", self.styles['BodyText']))
            
            if 'career_level_estimation' in analysis_data:
                story.append(Paragraph(f"<b>Career Level:</b> {analysis_data.get('career_level_estimation', 'N/A')}", self.styles['BodyText']))
            
            story.append(Spacer(1, 0.3*inch))
            
            # Executive Summary
            story.append(Paragraph("Executive Summary", self.styles['SectionHeader']))
            
            summary_data = []
            if 'overall_score' in analysis_data:
                summary_data.append(['Overall Score', f"{analysis_data['overall_score']}%"])
            if 'completeness_score' in analysis_data:
                summary_data.append(['Completeness Score', f"{analysis_data['completeness_score']}%"])
            if 'impact_score' in analysis_data:
                summary_data.append(['Impact Score', f"{analysis_data['impact_score']}%"])
            if 'professional_score' in analysis_data:
                summary_data.append(['Professional Score', f"{analysis_data['professional_score']}%"])
            if 'strong_verbs_used' in analysis_data:
                summary_data.append(['Strong Verbs Used', str(analysis_data['strong_verbs_used'])])
            
            if summary_data:
                table = Table(summary_data, colWidths=[3*inch, 2*inch])
                table.setStyle(TableStyle([
                    ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f8fafc')),
                    ('TEXTCOLOR', (0, 0), (-1, -1), colors.HexColor('#1e293b')),
                    ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 11),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
                    ('TOPPADDING', (0, 0), (-1, -1), 8),
                    ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0'))
                ]))
                story.append(table)
            
            story.append(Spacer(1, 0.2*inch))
            
            # Strengths
            if 'strengths' in analysis_data and analysis_data['strengths']:
                story.append(Paragraph("Strengths", self.styles['SectionHeader']))
                for strength in analysis_data['strengths']:
                    story.append(Paragraph(f"• {strength}", self.styles['BodyText']))
                story.append(Spacer(1, 0.1*inch))
            
            # Areas for Improvement
            if 'weaknesses' in analysis_data and analysis_data['weaknesses']:
                story.append(Paragraph("Areas for Improvement", self.styles['SectionHeader']))
                for weakness in analysis_data['weaknesses']:
                    story.append(Paragraph(f"• {weakness}", self.styles['BodyText']))
                story.append(Spacer(1, 0.1*inch))
            
            # Skills Identified
            if 'skills_found' in analysis_data and analysis_data['skills_found']:
                story.append(Paragraph("Skills Identified", self.styles['SectionHeader']))
                skills_text = ", ".join(analysis_data['skills_found'])
                story.append(Paragraph(skills_text, self.styles['BodyText']))
                story.append(Spacer(1, 0.1*inch))
            
            # Metrics & Verb Analysis
            if 'metrics_found' in analysis_data or 'strong_verbs_used' in analysis_data:
                story.append(Paragraph("Metrics & Verb Analysis", self.styles['SectionHeader']))
                
                if 'metrics_found' in analysis_data:
                    story.append(Paragraph(f"<b>Total Metrics Found:</b> {len(analysis_data.get('metrics_found', []))}", self.styles['BodyText']))
                if 'strong_verbs_used' in analysis_data:
                    story.append(Paragraph(f"<b>Strong Verbs Used:</b> {analysis_data['strong_verbs_used']}", self.styles['BodyText']))
                if 'weak_verbs_used' in analysis_data:
                    story.append(Paragraph(f"<b>Weak Verbs Used:</b> {analysis_data['weak_verbs_used']}", self.styles['BodyText']))
                
                story.append(Spacer(1, 0.1*inch))
            
            # Role Matching
            if 'role_analyzed' in analysis_data and analysis_data['role_analyzed']:
                story.append(Paragraph("Role Matching Analysis", self.styles['SectionHeader']))
                story.append(Paragraph(f"<b>Role Analyzed:</b> {analysis_data['role_analyzed']}", self.styles['BodyText']))
                
                if 'role_match_score' in analysis_data:
                    story.append(Paragraph(f"<b>Role Match Score:</b> {analysis_data['role_match_score']}%", self.styles['BodyText']))
                
                if 'matched_skills' in analysis_data and analysis_data['matched_skills']:
                    story.append(Paragraph(f"<b>Matched Skills:</b> {', '.join(analysis_data['matched_skills'])}", self.styles['BodyText']))
                
                if 'missing_role_skills' in analysis_data and analysis_data['missing_role_skills']:
                    story.append(Paragraph(f"<b>Missing Skills:</b> {', '.join(analysis_data['missing_role_skills'])}", self.styles['BodyText']))
                
                story.append(Spacer(1, 0.1*inch))
            
            # Top Priority Actions
            if 'improvement_priority' in analysis_data and analysis_data['improvement_priority']:
                story.append(Paragraph("Top Priority Actions", self.styles['SectionHeader']))
                for idx, priority in enumerate(analysis_data['improvement_priority'], 1):
                    story.append(Paragraph(f"{idx}. {priority}", self.styles['BodyText']))
                story.append(Spacer(1, 0.2*inch))
            
            # Footer
            story.append(Spacer(1, 0.3*inch))
            story.append(Paragraph("<i>Generated by AI Powered Resume Analyzer</i>", self.styles['BodyText']))
            story.append(Paragraph("<i>Confidential Report - For Candidate Use Only</i>", self.styles['BodyText']))
            
            doc.build(story)
            buffer.seek(0)
            return buffer
            
        except Exception as e:
            print(f"Error building PDF: {str(e)}")
            raise
