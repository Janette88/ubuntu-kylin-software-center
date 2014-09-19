#!/usr/bin/python
# -*- coding: utf-8 -*-

### BEGIN LICENSE

# Copyright (C) 2013 National University of Defense Technology(NUDT) & Kylin Ltd

# Author:
#     Shine Huang<shenghuang@ubuntukylin.com>
# Maintainer:
#     Shine Huang<shenghuang@ubuntukylin.com>

# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.

#**************************Add by zhangxin***************************#
import xapian
#********************************************************************#
import sqlite3
import os
import time
from PyQt4.QtGui import *
from PyQt4.QtCore import *
import multiprocessing
from backend.remote.piston_remoter import PistonRemoter
from utils.machine import *
from models.review import Review
from models.enums import UBUNTUKYLIN_SERVER,UBUNTUKYLIN_DATA_PATH,UKSC_CACHE_DIR,UnicodeToAscii

XAPIAN_DB_PATH = os.path.join(UKSC_CACHE_DIR, "xapiandb")


class SilentProcess(multiprocessing.Process):

    def __init__(self, squeue):
        super(SilentProcess, self).__init__()
        multiprocessing.Process.__init__(self)

        self.daemon = True
        self.squeue = squeue

        self.destFile = os.path.join(UKSC_CACHE_DIR,"uksc.db")
        self.connect = sqlite3.connect(self.destFile, check_same_thread=False)
        self.cursor = self.connect.cursor()

        self.premoter = PistonRemoter(service_root=UBUNTUKYLIN_SERVER)

    def run(self):
        while True:
            workqueuelen = self.squeue.qsize()
            # print "silent worklist size : ", str(workqueuelen)
            if workqueuelen == 0:
                time.sleep(1)
                continue

            item = self.squeue.get_nowait()

            print "silent process get one workitem : ", item.funcname

            if item.funcname == "get_all_ratings":
                self.get_all_ratings()
            elif item.funcname == "submit_pingback_main":
                self.submit_pingback_main()
            elif item.funcname == "submit_pingback_app":
                self.submit_pingback_app(item.kwargs)
            elif item.funcname == "get_all_categories":
                self.get_all_categories()
            elif item.funcname == "get_all_rank_and_recommend":
                self.get_all_rank_and_recommend()
            elif item.funcname == "get_newer_application_info":
                self.get_newer_application_info()
            #**************************************************#
            elif item.funcname == "update_xapiandb":
                self.update_xapiandb()            

    # update rating_avg and rating_total in cache db from server
    def get_all_ratings(self):
        reslist = self.premoter.get_all_ratings()

        for rating in reslist:
            app_name = rating['app_name']
            rating_avg = str(rating['rating_avg'])
            rating_total = str(rating['rating_total'])

            sql = "update application set rating_total=?,rating_avg=? where app_name=?"
            self.cursor.execute(sql, (rating_total,rating_avg,app_name))

        self.connect.commit()

        print "all ratings and rating_total update over : ",len(reslist)

    # submit pingback-main to server
    def submit_pingback_main(self):
        machine = get_machine_id()
        distro = get_distro_info()[0]
        version_os = get_distro_info()[1]
        version_uksc = get_uksc_version()

        res = self.premoter.submit_pingback_main(machine, distro, version_os, version_uksc)
        return res

    # submit pingback-app to server
    def submit_pingback_app(self, kwargs):
        app_name = kwargs["app_name"]
        isrcm = kwargs["isrcm"]
        machine = get_machine_id()
        res = self.premoter.submit_pingback_app(app_name, machine, isrcm)
        return res

    # get all categories data from server
    def get_all_categories(self):
        reslist = self.premoter.get_all_categories()

        for category in reslist:
            cid = category['id']
            name = category['name']
            display_name = category['display_name']
            priority = category['priority']

            sql = "select count(*) from category where id=?"
            self.cursor.execute(sql, (cid,))
            res = self.cursor.fetchall()
            isexist = ''
            for item in res:
                isexist = item[0]

            if(isexist == 1):   # id exist, update
                sql = "update category set name=?,display_name=?,priority=? where id=?"
                self.cursor.execute(sql, (name,display_name,priority,cid))
            else:               # id not exist, insert
                sql = "insert into category(id,name,display_name,priority,visible) values(?,?,?,?,1)"
                self.cursor.execute(sql, (cid,name,display_name,priority))

        self.connect.commit()

        print "all categories update over : ",len(reslist)

    # get all rank and recommend data from server
    def get_all_rank_and_recommend(self):
        reslist = self.premoter.get_all_rank_and_recommend()

        sql = "delete from rank"
        self.cursor.execute(sql)

        for rank in reslist:
            rid = rank['id']
            aid = rank['aid']['id']
            rank_rating = rank['rank_rating']
            rank_download = rank['rank_download']
            rank_recommend = rank['rank_recommend']
            rank_pointout = rank['rank_pointout']

            sql = "insert into rank(id,aid_id,rank_rating,rank_download,rank_recommend,rank_pointout) values(?,?,?,?,?,?)"
            self.cursor.execute(sql, (rid,aid,rank_rating,rank_download,rank_recommend,rank_pointout))

        self.connect.commit()

        print "all rank and recommend update over : ",len(reslist)

    # get newer application info from server
    def get_newer_application_info(self):
        # get application info last update date
        last_update_date = ''
        self.cursor.execute("select value from dict where key='appinfo_updatetime'")
        res = self.cursor.fetchall()
        for item in res:
            last_update_date = item[0]

        reslist = self.premoter.get_newer_application_info(last_update_date)

        # update application info to cache db
        for app in reslist:
            aid = app['id']
            app_name = app['app_name']
            display_name = app['display_name']
            display_name_cn = app['display_name_cn']
            categories = app['categories']
            summary = app['summary']
            description = app['description']
            command = app['command']
            rating_avg = app['rating_avg']
            rating_total = app['rating_total']
            review_total = app['review_total']
            download_total = app['download_total']

            sql = "select count(*) from application where id=?"
            self.cursor.execute(sql, (aid,))
            res = self.cursor.fetchall()
            isexist = ''
            for item in res:
                isexist = item[0]

            if(isexist == 1):   # id exist, update
                sql = "update application set app_name=?,display_name=?,display_name_cn=?,categories=?,summary=?,description=?,command=?,rating_avg=?,rating_total=?,review_total=?,download_total=? where id=?"
                self.cursor.execute(sql, (app_name,display_name,display_name_cn,categories,summary,description,command,rating_avg,rating_total,review_total,download_total,aid))
            else:               # id not exist, insert
                sql = "insert into application(id,app_name,display_name,display_name_cn,categories,summary,description,command,rating_avg,rating_total,review_total,download_total) values(?,?,?,?,?,?,?,?,?,?,?,?)"
                self.cursor.execute(sql, (aid,app_name,display_name,display_name_cn,categories,summary,description,command,rating_avg,rating_total,review_total,download_total))

        # set application info last update date
        nowdate = time.strftime('%Y-%m-%d',time.localtime())
        self.cursor.execute("update dict set value=? where key=?", (nowdate,'appinfo_updatetime'))

        self.connect.commit()

        print "all newer application info update over : ",len(reslist)
        
    #*************************update for xapiandb***********************************#
    def update_xapiandb(self):
    
        modified_num = 0
        add_num = 0
        xapiandb_update = "No"
                  
        database = xapian.WritableDatabase(XAPIAN_DB_PATH,xapian.DB_OPEN)
        DB = xapian.Database(database)
        enquire = xapian.Enquire(database)
            
        indexer = xapian.TermGenerator()

        query_xapiandb_version = xapian.Query("the_#ukxapiandb#_version")
        enquire.set_query(query_xapiandb_version)
        matches = enquire.get_mset(0,1)
        for re in matches:
            docid_for_xapiandb_version = re.document.get_docid()
            doc_for_xapiandb_version = re.document
            doc_data = doc_for_xapiandb_version.get_data()
            if ("XAPIANDB_VERSION" == doc_data):
                the_latest_update_time = doc_for_xapiandb_version.get_value(2) #valueslot:2 xapiandb update time
            else:
                the_latest_update_time = time.strftime('%Y-%m-%dT%H:%M:%S',time.localtime())
                print "Failed to get the latest update time from client xapiandb,use default time.localtime()"

        reslist = self.premoter.newerapp_for_xapianupdate(the_latest_update_time)
            
        for app in reslist:
            app_name = str(app["app_name"])
            display_name_cn = str(app["display_name_cn"])
            keywords_for_search = str(app["keywords_for_search"])
            
            query = xapian.Query(app_name)
            enquire.set_query(query)
            doccount = DB.get_doccount()
            matches = enquire.get_mset(0,doccount)
            if matches.size() != 0:
                for re in matches:
                    if re.document.get_data() == app_name:
                        docid = re.docid
                        doc = re.document
                        doc.clear_terms()
                        indexer.set_document(doc)
                        doc.add_term(app_name,10)
                        keywords = display_name_cn+";"+keywords_for_search+";"+app_name
                        indexer.index_text(keywords,10)
                        
                        try:
                            from mmseg.search import seg_txt_search,seg_txt_2_dict
                            for word,value in seg_txt_2_dict(keywords).iteritems():
                                if word != "none":
                                    doc.add_term(word,10)
                                else:
                                    pass 
                                                         
                        except:
                            print "No MMSEG for keywords segment"
                            
                        database.replace_document(docid,doc)
                        xapiandb_update = "Yes"
                        modified_num = modified_num + 1
                        
                    else:
                        continue
                
            else:
                doc = xapian.Document()
                doc.set_data(app_name)
                doc.add_term(app_name,10)
 
                indexer.set_document(doc)
                if keywords_for_search != "None":
                    keywords = display_name_cn+";"+keywords_for_search+";"+app_name
                else:
                    keywords = display_name_cn+";"+app_name
                indexer.index_text(keywords,10)
                
                try:
                    
                    for word,value in seg_txt_2_dict(keywords).iteritems():
                        if word != "none":
                            doc.add_term(word,10)
                        else:
                            print "No MMSEG for keywords segment"                           
                except:
                    pass
                database.add_document(doc)
                add_num = add_num + 1
                print "App:",doc.get_data(),"  ","terms:",
                for itr in doc.termlist():
                    print itr.term,
                xapiandb_update = "Yes"
                print "  "                
                    
        try:
            if xapiandb_update == "Yes":
                now = time.strftime('%Y-%m-%dT%H:%M:%S',time.localtime())
                doc_for_xapiandb_version.add_value(2,now)
                database.replace_document(docid_for_xapiandb_version,doc_for_xapiandb_version)
                all_update_is_done = "Yes"
                if "Yes" == all_update_is_done:
                    database.commit()
                    print "Xapiandb has updated . %d app modified, %d app add.  Tatal: %d app updated"%(modified_num,add_num,len(reslist))
                
                else:
                    print "Failed to update xapian database (/home/ice_bird/.cache/uksc/xapiandb)"
        except:
            print "The xapian database (/home/ice_bird/.cache/uksc/xapiandb) is crashed,please remove it and install a new one!"
        print "update uksc xapiandb over"
            
class SilentWorkerItem:

     def __init__(self, funcname, kwargs):
        self.funcname = funcname
        self.kwargs = kwargs

if __name__ == "__main__":
    pass